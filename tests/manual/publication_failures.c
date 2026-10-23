/*
 * Compile: cc -std=c11 -Wall -Wextra -O2 publication_failures.c -lyaml -o publication_failures
 * Run only from a disposable offline directory. Fixtures remain under its generated temp dir.
 * Retry wait durations are not measured. Only sleep is omitted (a PATH shim).
 */
#define _XOPEN_SOURCE 700
#include <yaml.h>
#include <fcntl.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

typedef struct { const char *id, *file, *job; int pipeline; } Workflow;
static const Workflow flows[] = {
    {"pipeline", ".github/workflows/pipeline.yml", "pipeline", 1},
    {"conference-sync", ".github/workflows/conference-sync.yml", "conference-sync", 0},
    {"conference-backfill", ".github/workflows/conference-backfill.yml", "backfill", 0},
    {"journal-sync", ".github/workflows/journal-sync.yml", "journal-sync", 0}
};
static const char *cases[] = {"success", "reject", "transient", "clean", "commit-fail", "stage-fail"};
static char root[PATH_MAX], source[PATH_MAX], sleep_bin[PATH_MAX];

static void die(const char *s) { perror(s); abort(); }
static void need(int ok, const char *s) { if (!ok) { fprintf(stderr, "harness error: %s\n", s); abort(); } }
static void path(char *out, size_t n, const char *a, const char *b) {
    int len = snprintf(out, n, "%s/%s", a, b);
    need(len >= 0 && (size_t)len < n, "path too long");
}
static void write_file(const char *p, const char *s, mode_t mode) {
    FILE *f = fopen(p, "w"); if (!f) die(p);
    int bad = fputs(s, f) == EOF;
    if (fclose(f)) bad = 1;
    if (bad) die("write file");
    if (chmod(p, mode)) die("chmod");
}
static void mkdir_ok(const char *p) {
    struct stat st;
    if (!mkdir(p, 0700)) return;
    need(stat(p, &st) == 0 && S_ISDIR(st.st_mode), "mkdir failed");
}
static int run(char *const av[], const char *cwd, const char *out, const char *log,
               const char *trace, const char *mode) {
    pid_t p = fork(); int st;
    if (p < 0) die("fork");
    if (!p) {
        int fd;
        if (cwd && chdir(cwd)) _exit(126);
        if (log) {
            fd = open(log, O_WRONLY | O_CREAT | O_APPEND, 0600); if (fd < 0) _exit(126);
            if (dup2(fd, STDERR_FILENO) < 0 || (!out && dup2(fd, STDOUT_FILENO) < 0)) _exit(126);
            close(fd);
        }
        if (out) { fd = open(out, O_WRONLY | O_CREAT | O_TRUNC, 0600); if (fd < 0 || dup2(fd, STDOUT_FILENO) < 0) _exit(126); close(fd); }
        if (trace) setenv("GIT_TRACE", trace, 1);
        if (mode) setenv("VERIFY_MODE", mode, 1);
        if (sleep_bin[0]) { const char *old = getenv("PATH"); char b[PATH_MAX * 2]; snprintf(b, sizeof b, "%s:%s", sleep_bin, old ? old : "/usr/bin:/bin"); setenv("PATH", b, 1); }
        execvp(av[0], av); _exit(127);
    }
    if (waitpid(p, &st, 0) < 0) die("waitpid");
    need(WIFEXITED(st), "child terminated by signal");
    return WEXITSTATUS(st);
}
static yaml_node_t *get(yaml_document_t *d, yaml_node_t *m, const char *key) {
    if (!m || m->type != YAML_MAPPING_NODE) return NULL;
    for (yaml_node_pair_t *p = m->data.mapping.pairs.start; p < m->data.mapping.pairs.top; p++) {
        yaml_node_t *k = yaml_document_get_node(d, p->key);
        if (k && k->type == YAML_SCALAR_NODE && !strcmp((char *)k->data.scalar.value, key))
            return yaml_document_get_node(d, p->value);
    }
    return NULL;
}
static int is(yaml_node_t *n, const char *s) {
    return n && n->type == YAML_SCALAR_NODE && !strcmp((char *)n->data.scalar.value, s);
}
static char *read_run(const Workflow *w) {
    char p[PATH_MAX]; path(p, sizeof p, source, w->file);
    FILE *f = fopen(p, "rb"); if (!f) die(p);
    yaml_parser_t parser; yaml_document_t doc;
    need(yaml_parser_initialize(&parser), "yaml parser init"); yaml_parser_set_input_file(&parser, f);
    need(yaml_parser_load(&parser, &doc), "parse workflow YAML");
    yaml_node_t *jobs = get(&doc, yaml_document_get_root_node(&doc), "jobs");
    yaml_node_t *job = get(&doc, jobs, w->job), *steps = get(&doc, job, "steps"), *run_node = NULL;
    if (steps && steps->type == YAML_SEQUENCE_NODE)
        for (yaml_node_item_t *i = steps->data.sequence.items.start; i < steps->data.sequence.items.top; i++) {
            yaml_node_t *step = yaml_document_get_node(&doc, *i);
            if (is(get(&doc, step, "name"), "Commit updated data")) { run_node = get(&doc, step, "run"); break; }
        }
    need(run_node && run_node->type == YAML_SCALAR_NODE, "missing named run scalar in selected job");
    char *r = strdup((char *)run_node->data.scalar.value); need(r != NULL, "copy run scalar");
    yaml_document_delete(&doc); yaml_parser_delete(&parser); fclose(f); return r;
}
static void setup(const Workflow *w, const char *which, char *repo, char *bare, const char *log) {
    char name[128], p[PATH_MAX];
    snprintf(name, sizeof name, "%s-%s", w->id, which); path(repo, PATH_MAX, root, name); need(mkdir(repo, 0700) == 0, "make repo");
    snprintf(name, sizeof name, "%s-%s-origin", w->id, which); path(bare, PATH_MAX, root, name);
    char *a1[] = {"git", "init", "--bare", "--template=", "--initial-branch=main", bare, NULL};
    char *a2[] = {"git", "-C", repo, "init", "--template=", "--initial-branch=main", NULL};
    need(!run(a1, NULL, NULL, log, NULL, NULL) && !run(a2, NULL, NULL, log, NULL, NULL), "git init");
    char *a3[] = {"git", "-C", repo, "config", "user.name", "test", NULL};
    char *a4[] = {"git", "-C", repo, "config", "user.email", "test@example.invalid", NULL};
    need(!run(a3, NULL, NULL, log, NULL, NULL) && !run(a4, NULL, NULL, log, NULL, NULL), "git config");
    path(p, sizeof p, repo, "site"); mkdir_ok(p);
    path(p, sizeof p, repo, "site/data"); mkdir_ok(p);
    path(p, sizeof p, repo, "data"); mkdir_ok(p);
    path(p, sizeof p, repo, ".git/hooks"); mkdir_ok(p);
    path(p, sizeof p, repo, "site/data/probe.json"); write_file(p, "original\n", 0600);
    path(p, sizeof p, repo, "data/probe.json"); write_file(p, "original\n", 0600);
    char *add[] = {"git", "-C", repo, "add", "site/data/probe.json", "data/probe.json", NULL};
    char *commit[] = {"git", "-C", repo, "commit", "-m", "seed", NULL};
    char *remote[] = {"git", "-C", repo, "remote", "add", "origin", bare, NULL};
    char *push[] = {"git", "-C", repo, "push", "-u", "origin", "main", NULL};
    need(!run(add, NULL, NULL, log, NULL, NULL) && !run(commit, NULL, NULL, log, NULL, NULL) &&
         !run(remote, NULL, NULL, log, NULL, NULL) && !run(push, NULL, NULL, log, NULL, NULL), "seed Git repository");
    if (strcmp(which, "clean")) { path(p, sizeof p, repo, "site/data/probe.json"); write_file(p, "generated\n", 0600); }
    if (!strcmp(which, "commit-fail")) { path(p, sizeof p, repo, ".git/hooks/commit-msg"); write_file(p, "#!/bin/sh\nexit 1\n", 0700); }
    if (!strcmp(which, "stage-fail")) { path(p, sizeof p, repo, ".git/index.lock"); write_file(p, "locked\n", 0600); }
    path(p, sizeof p, bare, "hooks"); mkdir_ok(p);
    path(p, sizeof p, bare, "hooks/pre-receive");
    write_file(p, "#!/bin/sh\nn=0; [ ! -f attempts ] || read n < attempts\nn=$((n+1)); printf '%s\\n' \"$n\" > attempts\ncase \"${VERIFY_MODE:-}\" in reject) exit 1;; transient) [ \"$n\" -lt 3 ] && exit 1;; esac\nexit 0\n", 0700);
}
static int capture(const char *repo, const char *log, const char *out, const char *verb, const char *rev) {
    char *av[] = {"git", "-C", (char *)repo, (char *)verb, (char *)rev, NULL};
    return run(av, NULL, out, log, NULL, NULL);
}
static void contents(const char *p, char *out, size_t n) {
    FILE *f = fopen(p, "r"); if (!f) die(p);
    size_t k = fread(out, 1, n - 1, f); out[k] = 0; fclose(f);
}
static int pushes(const char *trace) {
    FILE *f = fopen(trace, "r"); if (!f) return 0;
    char line[4096]; int n = 0; while (fgets(line, sizeof line, f)) if (strstr(line, "built-in: git push")) n++;
    fclose(f); return n;
}
static void sha(const char *repo, const char *log, const char *out, const char *ref) {
    need(!capture(repo, log, out, "rev-parse", ref), "git rev-parse");
}
int main(int argc, char **argv) {
    need(argc == 2 && argv[1][0] == '/', "usage: publication_failures ABS_REPO");
    need(realpath(argv[1], source) != NULL, "resolve source repository");
    char temp[] = "publication-failures.XXXXXX"; need(mkdtemp(temp) != NULL, "create temp root");
    need(realpath(temp, root) != NULL, "resolve temp root");
    char bin[PATH_MAX], sl[PATH_MAX]; path(bin, sizeof bin, root, "bin"); need(mkdir(bin, 0700) == 0, "make shim dir");
    path(sleep_bin, sizeof sleep_bin, bin, "");
    path(sl, sizeof sl, bin, "sleep"); write_file(sl, "#!/bin/sh\nexit 0\n", 0700);
    setenv("GIT_CONFIG_NOSYSTEM", "1", 1); setenv("GIT_CONFIG_GLOBAL", "/dev/null", 1); setenv("GIT_TERMINAL_PROMPT", "0", 1);
    setenv("GIT_AUTHOR_NAME", "test", 1); setenv("GIT_AUTHOR_EMAIL", "test@example.invalid", 1);
    setenv("GIT_COMMITTER_NAME", "test", 1); setenv("GIT_COMMITTER_EMAIL", "test@example.invalid", 1);
    int failures = 0;
    for (size_t wi = 0; wi < sizeof flows / sizeof flows[0]; wi++) {
        char *script = read_run(&flows[wi]);
        for (size_t ci = 0; ci < sizeof cases / sizeof cases[0]; ci++) {
            char repo[PATH_MAX], bare[PATH_MAX], log[PATH_MAX], trace[PATH_MAX], out[PATH_MAX], before[128], after[128], val[128];
            char tag[160]; snprintf(tag, sizeof tag, "%s-%s", flows[wi].id, cases[ci]);
            char logname[180]; snprintf(logname, sizeof logname, "%s.log", tag); path(log, sizeof log, root, logname);
            setup(&flows[wi], cases[ci], repo, bare, log); path(trace, sizeof trace, repo, ".git/trace");
            char outname[200]; snprintf(outname, sizeof outname, "%s.sha.before", tag); path(out, sizeof out, root, outname); sha(repo, log, out, "HEAD"); contents(out, before, sizeof before);
            snprintf(outname, sizeof outname, "%s.sha.remote.before", tag); path(out, sizeof out, root, outname); sha(bare, log, out, "refs/heads/main"); contents(out, after, sizeof after);
            char *bash[] = {"/bin/bash", "--noprofile", "--norc", "-e", "-c", script, NULL};
            int status = run(bash, repo, NULL, log, trace, cases[ci]), npush = pushes(trace);
            snprintf(outname, sizeof outname, "%s.sha.after", tag); path(out, sizeof out, root, outname); sha(repo, log, out, "HEAD"); contents(out, val, sizeof val); int lc = strcmp(before, val) != 0;
            snprintf(outname, sizeof outname, "%s.sha.remote.after", tag); path(out, sizeof out, root, outname); sha(bare, log, out, "refs/heads/main"); contents(out, val, sizeof val); int rc = strcmp(after, val) != 0;
            snprintf(outname, sizeof outname, "%s.local.data", tag); path(out, sizeof out, root, outname); need(!capture(repo, log, out, "show", "HEAD:site/data/probe.json"), "git show local data"); contents(out, val, sizeof val); int ld = !strcmp(val, "generated\n");
            snprintf(outname, sizeof outname, "%s.remote.data", tag); path(out, sizeof out, root, outname); need(!capture(bare, log, out, "show", "refs/heads/main:site/data/probe.json"), "git show remote data"); contents(out, val, sizeof val); int rd = !strcmp(val, "generated\n");
            int want_fail = !strcmp(cases[ci], "reject") || (!strcmp(cases[ci], "transient") && flows[wi].pipeline) || !strcmp(cases[ci], "commit-fail") || !strcmp(cases[ci], "stage-fail");
            int wp = !strcmp(cases[ci], "success") ? 1 : !strcmp(cases[ci], "reject") ? flows[wi].pipeline ? 1 : 3 :
                !strcmp(cases[ci], "transient") ? flows[wi].pipeline ? 1 : 3 : 0;
            int wl = !strcmp(cases[ci], "success") || !strcmp(cases[ci], "reject") || !strcmp(cases[ci], "transient");
            int wr = !strcmp(cases[ci], "success") || (!strcmp(cases[ci], "transient") && !flows[wi].pipeline);
            int ok = (!!status == want_fail) && npush == wp && lc == wl && rc == wr && ld == wl && rd == wr;
            printf("%s/%s status=%d pushes=%d local_changed=%d remote_changed=%d ok=%s\n", flows[wi].id, cases[ci], status, npush, lc, rc, ok ? "true" : "false");
            if (!ok) { fprintf(stderr, "details: %s\n", log); failures++; }
        }
        free(script);
    }
    return failures ? 1 : 0;
}
