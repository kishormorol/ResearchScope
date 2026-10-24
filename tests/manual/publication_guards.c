#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <fcntl.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>
#include <yaml.h>

// Run in an isolated directory: cc -O2 tests/manual/publication_guards.c -lyaml -o check-guards
// Then run ./check-guards REPO. This checks local shell behavior, not hosted Actions.
static yaml_node_t *field(yaml_document_t *doc, yaml_node_t *node, const char *key) {
    assert(node && node->type == YAML_MAPPING_NODE);
    for (yaml_node_pair_t *pair = node->data.mapping.pairs.start;
         pair < node->data.mapping.pairs.top; pair++) {
        yaml_node_t *name = yaml_document_get_node(doc, pair->key);
        assert(name && name->type == YAML_SCALAR_NODE);
        if (!strcmp((char *)name->data.scalar.value, key))
            return yaml_document_get_node(doc, pair->value);
    }
    return NULL;
}

static int run_guard(const char *script, const char *ref) {
    pid_t child = fork();
    assert(child >= 0);
    if (!child) {
        if (ref) {
            if (setenv("GITHUB_REF", ref, 1)) _exit(125);
        } else if (unsetenv("GITHUB_REF")) _exit(125);
        int sink = open("/dev/null", O_WRONLY);
        if (sink < 0 || dup2(sink, STDOUT_FILENO) < 0 ||
            dup2(sink, STDERR_FILENO) < 0) _exit(125);
        close(sink);
        execl("/bin/bash", "bash", "--noprofile", "--norc", "-e", "-o",
              "pipefail", "-c", script, (char *)NULL);
        _exit(126);
    }
    int status;
    assert(waitpid(child, &status, 0) == child);
    assert(WIFEXITED(status));
    return WEXITSTATUS(status);
}

int main(int argc, char **argv) {
    assert(argc == 2);
    const char *jobs[][2] = {
        {"update", "update-data"}, {"pipeline", "pipeline"},
        {"pipeline", "build-sections"}, {"backfill", "backfill"},
        {"conference-sync", "conference-sync"}, {"conference-backfill", "backfill"},
        {"journal-sync", "journal-sync"}, {"deploy", "deploy"},
        {"sections", "build-sections"}, {"register-sections-config", "register"},
        {"hf-space", "sync"},
    };
    const char *refs[] = {
        "refs/heads/main", "refs/heads/feature/x", "refs/tags/main",
        "refs/heads/main-extra", "refs/heads/feature/main",
        "refs/pull/1/merge", "main", "", NULL,
    };
    size_t checks = 0;
    for (size_t i = 0; i < sizeof(jobs) / sizeof(jobs[0]); i++) {
        char path[PATH_MAX];
        int length = snprintf(path, sizeof(path), "%s/.github/workflows/%s.yml",
                              argv[1], jobs[i][0]);
        assert(length > 0 && (size_t)length < sizeof(path));
        FILE *file = fopen(path, "rb");
        assert(file);
        struct stat info;
        assert(!fstat(fileno(file), &info) && S_ISREG(info.st_mode) &&
               info.st_size > 0 && info.st_size <= 65536);
        yaml_parser_t parser;
        yaml_document_t doc;
        assert(yaml_parser_initialize(&parser));
        yaml_parser_set_input_file(&parser, file);
        assert(yaml_parser_load(&parser, &doc));
        yaml_node_t *root = yaml_document_get_root_node(&doc);
        yaml_node_t *job = field(&doc, field(&doc, root, "jobs"), jobs[i][1]);
        yaml_node_t *steps = field(&doc, job, "steps");
        assert(steps && steps->type == YAML_SEQUENCE_NODE &&
               steps->data.sequence.items.start < steps->data.sequence.items.top);
        yaml_node_t *first = yaml_document_get_node(&doc, *steps->data.sequence.items.start);
        assert(!field(&doc, first, "if") && !field(&doc, first, "uses") &&
               !field(&doc, first, "continue-on-error") && !field(&doc, first, "env"));
        yaml_node_t *shell = field(&doc, first, "shell");
        yaml_node_t *run = field(&doc, first, "run");
        assert(shell && shell->type == YAML_SCALAR_NODE &&
               !strcmp((char *)shell->data.scalar.value, "bash"));
        assert(run && run->type == YAML_SCALAR_NODE && run->data.scalar.length);
        for (size_t j = 0; j < sizeof(refs) / sizeof(refs[0]); j++) {
            int status = run_guard((char *)run->data.scalar.value, refs[j]);
            if (status != (j == 0 ? 0 : 1)) {
                fprintf(stderr, "%s job=%s ref=%s status=%d\n", path, jobs[i][1],
                        refs[j] ? refs[j] : "<unset>", status);
                return 1;
            }
            checks++;
        }
        printf("PASS %s job=%s refs=9 guard=first\n", jobs[i][0], jobs[i][1]);
        yaml_document_delete(&doc);
        yaml_parser_delete(&parser);
        fclose(file);
    }
    printf("PASS guard cases=%zu\n", checks);
    return 0;
}
