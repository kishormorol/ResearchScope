#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <dirent.h>
#include <fcntl.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>
#include <yaml.h>

// Run in offline scratch: cc -O2 pages_publisher.c -lyaml -o check-pages
// Then ./check-pages BEFORE AFTER SCRATCH. This does not emulate hosted Actions.
typedef struct { yaml_document_t doc; yaml_node_t *root; } Doc;
static yaml_node_t *field(Doc *d, yaml_node_t *n, const char *key) {
    if (!n) return NULL;
    assert(n->type == YAML_MAPPING_NODE);
    for (yaml_node_pair_t *p = n->data.mapping.pairs.start; p < n->data.mapping.pairs.top; p++) {
        yaml_node_t *k = yaml_document_get_node(&d->doc, p->key);
        if (!strcmp((char *)k->data.scalar.value, key)) return yaml_document_get_node(&d->doc, p->value);
    }
    return NULL;
}
static int text(yaml_node_t *n, const char *s) {
    return n && n->type == YAML_SCALAR_NODE && !strcmp((char *)n->data.scalar.value, s);
}
static Doc load(const char *repo, const char *name) {
    char path[PATH_MAX];
    int len = snprintf(path, sizeof(path), "%s/.github/workflows/%s.yml", repo, name);
    assert(len > 0 && (size_t)len < sizeof(path));
    FILE *f = fopen(path, "rb"); assert(f);
    struct stat st; assert(!fstat(fileno(f), &st) && S_ISREG(st.st_mode) && st.st_size <= 65536);
    yaml_parser_t parser; assert(yaml_parser_initialize(&parser));
    yaml_parser_set_input_file(&parser, f);
    Doc d; assert(yaml_parser_load(&parser, &d.doc));
    d.root = yaml_document_get_root_node(&d.doc); assert(d.root);
    yaml_document_t end; assert(yaml_parser_load(&parser, &end));
    assert(!yaml_document_get_root_node(&end)); yaml_document_delete(&end);
    yaml_parser_delete(&parser); fclose(f); return d;
}
static int equal(Doc *a, yaml_node_t *x, Doc *b, yaml_node_t *y) {
    if (!x || !y) return x == y;
    if (x->type != y->type) return 0;
    if (x->type == YAML_SCALAR_NODE) return text(y, (char *)x->data.scalar.value);
    if (x->type == YAML_SEQUENCE_NODE) {
        yaml_node_item_t *i = x->data.sequence.items.start, *j = y->data.sequence.items.start;
        for (; i < x->data.sequence.items.top && j < y->data.sequence.items.top; i++, j++)
            if (!equal(a, yaml_document_get_node(&a->doc, *i), b, yaml_document_get_node(&b->doc, *j))) return 0;
        return i == x->data.sequence.items.top && j == y->data.sequence.items.top;
    }
    assert(x->type == YAML_MAPPING_NODE);
    if (x->data.mapping.pairs.top - x->data.mapping.pairs.start !=
        y->data.mapping.pairs.top - y->data.mapping.pairs.start) return 0;
    for (yaml_node_pair_t *p = x->data.mapping.pairs.start; p < x->data.mapping.pairs.top; p++) {
        yaml_node_t *k = yaml_document_get_node(&a->doc, p->key);
        if (!equal(a, yaml_document_get_node(&a->doc, p->value), b, field(b, y, (char *)k->data.scalar.value))) return 0;
    }
    return 1;
}
static yaml_node_t *job(Doc *d, const char *name) { return field(d, field(d, d->root, "jobs"), name); }
static int publication_step(Doc *d, yaml_node_t *step) {
    yaml_node_t *name = field(d, step, "name");
    return text(name, "Require main branch") || text(name, "Commit updated data") ||
        text(name, "Commit backfilled data") || text(name, "Upload generated data recovery");
}
static int generation_equal(Doc *a, yaml_node_t *x, Doc *b, yaml_node_t *y) {
    for (yaml_node_pair_t *p = x->data.mapping.pairs.start; p < x->data.mapping.pairs.top; p++) {
        yaml_node_t *key = yaml_document_get_node(&a->doc, p->key);
        if (!text(key, "steps") && !equal(a, yaml_document_get_node(&a->doc, p->value),
            b, field(b, y, (char *)key->data.scalar.value))) return 0;
    }
    yaml_node_t *xs = field(a, x, "steps"), *ys = field(b, y, "steps");
    yaml_node_item_t *i = xs->data.sequence.items.start, *j = ys->data.sequence.items.start;
    for (;;) {
        while (i < xs->data.sequence.items.top && publication_step(a, yaml_document_get_node(&a->doc, *i))) i++;
        while (j < ys->data.sequence.items.top && publication_step(b, yaml_document_get_node(&b->doc, *j))) j++;
        if (i == xs->data.sequence.items.top || j == ys->data.sequence.items.top)
            return i == xs->data.sequence.items.top && j == ys->data.sequence.items.top;
        if (!equal(a, yaml_document_get_node(&a->doc, *i++), b, yaml_document_get_node(&b->doc, *j++))) return 0;
    }
}
static yaml_node_t *step(Doc *d, yaml_node_t *j, const char *key, const char *value) {
    yaml_node_t *s = field(d, j, "steps"); assert(s && s->type == YAML_SEQUENCE_NODE);
    for (yaml_node_item_t *p = s->data.sequence.items.start; p < s->data.sequence.items.top; p++) {
        yaml_node_t *n = yaml_document_get_node(&d->doc, *p);
        if (text(field(d, n, key), value)) return n;
    }
    return NULL;
}
static void emit(const char *dir, const char *name, yaml_node_t *run) {
    assert(run && run->type == YAML_SCALAR_NODE);
    char path[PATH_MAX]; int len = snprintf(path, sizeof(path), "%s/%s", dir, name);
    assert(len > 0 && (size_t)len < sizeof(path));
    FILE *f = fopen(path, "wx"); assert(f);
    assert(fwrite(run->data.scalar.value, 1, run->data.scalar.length, f) == run->data.scalar.length);
    assert(!fclose(f));
}
static void guard(Doc *d, yaml_node_t *j) {
    yaml_node_t *s = field(d, j, "steps");
    yaml_node_t *first = yaml_document_get_node(&d->doc, *s->data.sequence.items.start);
    assert(text(field(d, first, "name"), "Require main branch"));
    assert(text(field(d, first, "shell"), "bash") && !field(d, first, "if"));
    yaml_node_t *run = field(d, first, "run"); assert(run && run->type == YAML_SCALAR_NODE);
    const char *refs[] = {"refs/heads/main", "refs/heads/feature/x", "refs/tags/main",
        "refs/heads/main-extra", "refs/heads/feature/main", "refs/pull/1/merge", "main", "", NULL};
    for (size_t i = 0; i < sizeof(refs)/sizeof(*refs); i++) {
        pid_t pid = fork(); assert(pid >= 0);
        if (!pid) {
            if (refs[i]) { if (setenv("GITHUB_REF", refs[i], 1)) _exit(125); }
            else if (unsetenv("GITHUB_REF")) _exit(125);
            int sink = open("/dev/null", O_WRONLY);
            if (sink < 0 || dup2(sink, 1) < 0 || dup2(sink, 2) < 0) _exit(125);
            close(sink); execl("/bin/bash", "bash", "--noprofile", "--norc", "-e", "-o", "pipefail",
                "-c", (char *)run->data.scalar.value, (char *)NULL); _exit(126);
        }
        int status; assert(waitpid(pid, &status, 0) == pid && WIFEXITED(status));
        assert(WEXITSTATUS(status) == (i ? 1 : 0));
    }
}
int main(int argc, char **argv) {
    assert(argc == 4);
    const char *producers[][3] = {{"update","update-data","deploy-pages"}, {"pipeline","pipeline","deploy"},
        {"backfill","backfill","deploy"}, {"conference-backfill","backfill","deploy"},
        {"conference-sync","conference-sync","deploy"}, {"journal-sync","journal-sync","deploy"}};
    for (size_t i = 0; i < sizeof(producers)/sizeof(*producers); i++) {
        Doc a = load(argv[1], producers[i][0]), b = load(argv[2], producers[i][0]);
        assert(generation_equal(&a, job(&a, producers[i][1]), &b, job(&b, producers[i][1])));
        assert(equal(&a, field(&a, a.root, "on"), &b, field(&b, b.root, "on")));
        yaml_node_t *old = job(&a, producers[i][2]), *call = job(&b, producers[i][2]);
        assert(equal(&a, field(&a, old, "if"), &b, field(&b, call, "if")));
        assert(text(field(&b, call, "needs"), producers[i][1]));
        assert(text(field(&b, call, "uses"), "./.github/workflows/deploy.yml"));
        assert(!field(&b, call, "steps") && !field(&b, call, "runs-on"));
        yaml_node_t *perms = field(&b, b.root, "permissions");
        assert(text(field(&b, perms, "contents"), "write") && perms->data.mapping.pairs.top - perms->data.mapping.pairs.start == 1);
        perms = field(&b, call, "permissions");
        assert(text(field(&b, perms, "contents"), "read") && text(field(&b, perms, "pages"), "write") &&
               text(field(&b, perms, "id-token"), "write") && !field(&b, perms, "actions"));
        assert(text(field(&b, field(&b, call, "secrets"), "HF_TOKEN"), "${{ secrets.HF_TOKEN }}"));
        if (!i) emit(argv[3], "old-overlay.sh", field(&a, step(&a, old, "name", "Copy data into site/data/"), "run"));
        if (!strcmp(producers[i][0], "pipeline"))
            assert(generation_equal(&a, job(&a, "build-sections"), &b, job(&b, "build-sections")));
        yaml_document_delete(&a.doc); yaml_document_delete(&b.doc);
    }
    Doc d = load(argv[2], "deploy"), h = load(argv[2], "hf-space");
    yaml_node_t *deploy = job(&d, "deploy"), *sync = job(&d, "sync-space"), *mirror = job(&h, "sync");
    assert(text(field(&d, deploy, "if"), "github.repository == 'kishormorol/ResearchScope'"));
    assert(text(field(&h, mirror, "if"), "github.repository == 'kishormorol/ResearchScope'"));
    assert(text(field(&h, mirror, "timeout-minutes"), "10"));
    guard(&d, deploy); guard(&h, mirror);
    yaml_node_t *checkout = step(&d, deploy, "uses", "actions/checkout@v7");
    assert(text(field(&d, field(&d, checkout, "with"), "ref"), "main"));
    assert(text(field(&d, field(&d, checkout, "with"), "persist-credentials"), "false"));
    assert(text(field(&d, field(&d, step(&d, deploy, "uses", "actions/upload-pages-artifact@v5"), "with"), "path"), "site/"));
    assert(text(field(&d, sync, "needs"), "deploy") && !field(&d, sync, "if"));
    assert(text(field(&d, sync, "uses"), "./.github/workflows/hf-space.yml"));
    assert(text(field(&d, field(&d, deploy, "outputs"), "source_sha"), "${{ steps.source.outputs.sha }}"));
    assert(text(field(&d, field(&d, sync, "with"), "source_sha"), "${{ needs.deploy.outputs.source_sha }}"));
    assert(text(field(&d, field(&d, sync, "permissions"), "contents"), "read"));
    assert(text(field(&h, field(&h, step(&h, mirror, "uses", "actions/checkout@v4"), "with"), "ref"), "${{ inputs.source_sha || github.sha }}"));
    assert(text(field(&h, field(&h, step(&h, mirror, "name", "Upload to the Space"), "env"), "SOURCE_SHA"), "${{ steps.source.outputs.sha }}"));
    assert(!field(&h, field(&h, h.root, "on"), "workflow_run"));
    assert(field(&d, field(&d, d.root, "on"), "workflow_call") && field(&h, field(&h, h.root, "on"), "workflow_call"));
    assert(field(&d, field(&d, d.root, "on"), "workflow_dispatch") && field(&h, field(&h, h.root, "on"), "workflow_dispatch"));
    yaml_node_t *branches = field(&d, field(&d, field(&d, d.root, "on"), "push"), "branches");
    assert(branches && branches->type == YAML_SEQUENCE_NODE &&
        branches->data.sequence.items.top - branches->data.sequence.items.start == 1 &&
        text(yaml_document_get_node(&d.doc, *branches->data.sequence.items.start), "main"));
    assert(text(field(&d, field(&d, d.root, "concurrency"), "group"), "pages"));
    assert(text(field(&d, field(&d, d.root, "concurrency"), "queue"), "max"));
    assert(text(field(&d, field(&d, d.root, "concurrency"), "cancel-in-progress"), "false"));
    assert(text(field(&h, field(&h, h.root, "concurrency"), "queue"), "max"));
    emit(argv[3], "pages-source.sh", field(&d, step(&d, deploy, "id", "source"), "run"));
    emit(argv[3], "mirror-source.sh", field(&h, step(&h, mirror, "id", "source"), "run"));
    emit(argv[3], "stage.sh", field(&h, step(&h, mirror, "name", "Stage the site"), "run"));
    emit(argv[3], "token.sh", field(&h, step(&h, mirror, "name", "Check for a Hugging Face token"), "run"));
    yaml_document_delete(&d.doc); yaml_document_delete(&h.doc);
    char path[PATH_MAX]; int len = snprintf(path, sizeof(path), "%s/.github/workflows", argv[2]);
    assert(len > 0 && (size_t)len < sizeof(path)); DIR *dir = opendir(path); assert(dir);
    struct dirent *entry; size_t owners = 0;
    while ((entry = readdir(dir))) {
        size_t n = strlen(entry->d_name); if (n < 5 || strcmp(entry->d_name+n-4, ".yml")) continue;
        char name[NAME_MAX+1]; memcpy(name, entry->d_name, n-4); name[n-4] = 0;
        Doc w = load(argv[2], name); yaml_node_t *jobs = field(&w, w.root, "jobs");
        for (yaml_node_pair_t *p = jobs->data.mapping.pairs.start; p < jobs->data.mapping.pairs.top; p++) {
            yaml_node_t *j = yaml_document_get_node(&w.doc, p->value), *s = field(&w, j, "steps");
            if (!s) continue;
            for (yaml_node_item_t *v = s->data.sequence.items.start; v < s->data.sequence.items.top; v++) {
                yaml_node_t *use = field(&w, yaml_document_get_node(&w.doc, *v), "uses");
                if (use && !strncmp((char *)use->data.scalar.value, "actions/deploy-pages@", 21)) owners++;
            }
        }
        yaml_document_delete(&w.doc);
    }
    closedir(dir); assert(owners == 1);
    puts("PASS preserved generation steps in 6 producers, triggers=6 independent sections=1 calls=6 guards=18 Pages action owners=1");
    return 0;
}
