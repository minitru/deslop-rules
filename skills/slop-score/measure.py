#!/usr/bin/env python3
"""
slop-score: measure a codebase against the rules in AGENTS.md and print one number.

    python3 measure.py <directory> [--json]

0 is clean, 100 is slop. The number comes only from what this script counts, so the same tree always gets the same
score and a "before" can be compared with an "after". Function-level measures cover JavaScript/TypeScript, Go and
Python; other languages get the file-level measures (size, repeats, leftovers, secrets, exemptions).

The counts are heuristics (line and indentation based, no parser, no dependencies). They name the worst offenders so
a reader can check them. There is no ignore list and no flag to switch a measure off: fix the case, not the scan.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict

LANGS = {'.js': 'js', '.mjs': 'js', '.cjs': 'js', '.jsx': 'js', '.ts': 'js', '.tsx': 'js', '.go': 'go', '.py': 'py'}
OTHER_CODE = {'.java', '.kt', '.rs', '.cs', '.php', '.rb', '.swift', '.c', '.cc', '.cpp', '.h', '.hpp', '.scala', '.sh'}
SKIP_DIRS = {'.git', 'node_modules', 'vendor', 'dist', 'build', 'out', 'target', 'coverage', '.next', '.nuxt',
             '__pycache__', '.venv', 'venv', 'env', 'third_party', '.tox', '.mypy_cache', '.pytest_cache', 'bower_components'}
LOCKFILES = {'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'go.sum', 'poetry.lock', 'Cargo.lock', 'composer.lock'}
CLIENT_DIRS = {'public', 'static', 'client', 'frontend', 'www', 'web', 'assets', 'ui', 'components', 'pages', 'views', 'templates'}
MAX_BYTES = 1500000

TEST_RE = re.compile(r'(^|/)(tests?|__tests__|specs?|testdata|fixtures|__mocks__|e2e)/|\.(test|spec)\.[a-z]+$|_test\.(go|py)$|(^|/)test_[^/]*\.py$|(^|/)conftest\.py$')
LEFTOVER_RE = re.compile(r'(\.(bak|orig|old|rej|swp|tmp|backup)$|\.bak[-._]|~$| copy( \d+)?\.|[-_.](old|bak|copy)\.[a-z]+$)', re.I)
NO_TRACK_RE = re.compile(r'(^|/)(\.env(\.(?!example|sample|template|dist|defaults|test)[\w-]+)?|id_rsa|id_ed25519|id_ecdsa|[^/]*\.(p12|pfx|keystore|jks))$')

# ---------------------------------------------------------------- patterns per language
JS_FUNC = [
    (re.compile(r'^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)?\s*[(<]'), 'function'),
    (re.compile(r'^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*(?:async\s+)?(?:function\b|\([^)]*\)\s*(?::[^=]+)?=>|\(\s*$|[A-Za-z_$][\w$]*\s*=>)'), 'function'),
    (re.compile(r'^\s*(?:module\.)?exports\.([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?(?:function\b|\()'), 'function'),
    (re.compile(r'^\s+(?:(?:static|async|public|private|protected|override|get|set)\s+)*([A-Za-z_$#][\w$]*)\s*\([^)]*\)\s*(?::[^{]+)?\{\s*$'), 'method'),
]
JS_HANDLER = re.compile(r'^\s*[A-Za-z_$][\w$.]*\.(get|post|put|patch|delete|all)\(\s*[\'"`]([^\'"`]*)[\'"`]')
JS_KW = {'if', 'for', 'while', 'switch', 'catch', 'with', 'return', 'function', 'else', 'do', 'try', 'await', 'typeof', 'new'}
GO_FUNC = re.compile(r'^func\s+(\([^)]*\)\s*)?([A-Za-z_]\w*)\s*[(\[]')
PY_DEF = re.compile(r'^(\s*)(?:async\s+)?def\s+(\w+)\s*\(')

HTTP_FILE = {
    'js': re.compile(r'\b[A-Za-z_$][\w$]*\.(get|post|put|patch|delete|all)\(\s*[\'"`]/|export\s+(async\s+)?function\s+(GET|POST|PUT|PATCH|DELETE)\b|\(\s*req(uest)?\s*,\s*res(ponse)?\b'),
    'go': re.compile(r'http\.ResponseWriter|\*gin\.Context|echo\.Context|\*fiber\.Ctx|\*http\.Request'),
    'py': re.compile(r'^\s*@\w[\w.]*\.(route|get|post|put|patch|delete)\(|^\s*def\s+\w+\(\s*(self\s*,\s*)?request\b|\b(APIView|ViewSet)\b', re.M),
}
JS_NOT_MODELS = r'(?!Object\b|Array\b|Promise\b|JSON\b|Math\b|Date\b|Buffer\b|Number\b|String\b|Set\b|Map\b|Error\b|URL\b|Intl\b|Reflect\b|Symbol\b|RegExp\b)'
DB_CALL = {
    'js': re.compile(r'\b' + JS_NOT_MODELS + r'[A-Z][A-Za-z0-9]*\.(find|findOne|findById|findByIdAndUpdate|findByIdAndDelete|findOneAndUpdate|findOneAndDelete|updateOne|updateMany|deleteOne|deleteMany|insertMany|insertOne|create|aggregate|countDocuments|estimatedDocumentCount|distinct|bulkWrite|findAll|findByPk|destroy|upsert|exists)\('
                     r'|\bprisma\.\w+\.\w+\(|\b(db|pool|client|knex|conn|connection|sequelize|pg|mysql)\.(query|execute|raw|collection)\(|\bknex\(|\.save\(\)'),
    'go': re.compile(r'\b\w*(db|DB|tx|Tx|conn|Conn|pool|Pool|stmt|Stmt|store|Store|repo|Repo)\w*\.(Query|QueryRow|Exec|QueryContext|QueryRowContext|ExecContext|Prepare|Begin|BeginTx|Select|NamedExec|Where|Find|First|Create|Save|Delete|Model|Raw|Collection)\(|\bsql\.Open\('),
    'py': re.compile(r'\b(session|cursor|conn|connection|engine|db)\.(session\.)?(query|execute|executemany|add|add_all|commit|delete|merge|scalars|scalar|get)\(|\.objects\.(filter|get|all|create|exclude|update|delete|bulk_create|get_or_create|update_or_create|count|first|last|values|annotate|aggregate)\b'),
}
INNER_IMPORT = {
    'js': re.compile(r'\brequire\(\s*[\'"`]|\bawait\s+import\('),
    'py': re.compile(r'^\s+(import\s+\w|from\s+[\w.]+\s+import\s)'),
}
SWALLOW = {
    'js': re.compile(r'\bcatch\s*(\([^)]*\))?\s*\{\s*\}|\.catch\(\s*(\(\s*\w*\s*\)|\w+)\s*=>\s*(\{\s*\}|null|undefined|void 0)\s*\)'),
    'go': re.compile(r'^\s*_\s*=\s*[\w.]+\(|^\s*[\w.]+\s*,\s*_\s*:?=\s*(?!.*\.\()[\w.]+\('),
    'py': re.compile(r'^\s*except\b[^:]*:\s*(pass\b|\.\.\.)|^\s*except\s*:'),
}
HTML_RE = re.compile(r'</?(?:div|span|html|head|body|table|tr|td|th|h[1-6]|ul|ol|li|form|input|button|script|style|section|nav|header|footer|label|select|option|textarea|strong|img|br|p|a)(?:\s[^<>]*)?/?>')
EXEMPT_RE = re.compile(r'eslint-disable|@ts-ignore|@ts-nocheck|//\s*nolint|#\s*noqa|#\s*type:\s*ignore|pylint:\s*disable|istanbul ignore|#\s*nosec|\b(it|test|describe)\.skip\(|\bx(it|describe)\(|\bt\.Skip\(|@pytest\.mark\.skip|@unittest\.skip')
SECRET_PATTERNS = [
    ('private key block', re.compile(r'-{5}BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY(?: BLOCK)?-{5}(?:\\n|\\r|\s)*[A-Za-z0-9+/=]{40,}')),
    ('AWS access key id', re.compile(r'\b(?:AKIA|ASIA)[0-9A-Z]{16}\b')),
    ('GitHub token', re.compile(r'\bgh[pousr]_[A-Za-z0-9]{36}\b|\bgithub_pat_[A-Za-z0-9_]{60,}')),
    ('Slack token', re.compile(r'\bxox[abprs]-[A-Za-z0-9-]{10,}')),
    ('Stripe live key', re.compile(r'\b[sr]k_live_[A-Za-z0-9]{16,}')),
    ('Google API key (public by design if it is a Firebase web key: check its restrictions)', re.compile(r'\bAIza[0-9A-Za-z_-]{35}\b')),
    ('hard-coded credential', re.compile(r'(?i)\b(?:api[_-]?key|secret|passwd|password|token)[\w-]*["\']?\s*[:=]\s*["\'](?=[^"\']*[0-9])(?=[^"\']*[A-Za-z])[A-Za-z0-9/+_=-]{24,}["\']')),
]
KEY_HEADER = re.compile(r'-{5}BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY(?: BLOCK)?-{5}\s*$')
PLACEHOLDER_RE = re.compile(r'(?i)process\.env|os\.environ|getenv|example|placeholder|changeme|your[_-]|xxxx|dummy|sample|<[a-z_ -]+>')
IMPORT_LINE = re.compile(r'^(import\b|from\s+\S+\s+import\b|(const|let|var)\s+.*=\s*require\(|require\(|use\s+\w|#include|package\s+\w|"[\w./-]+"$|export\s+\{[^}]*\}\s+from)')
GENERIC_NAMES = {'main', 'init', 'setup', 'run', 'start', 'stop', 'close', 'handler', 'handle', 'default', 'index', 'render', 'update',
                 'create', 'delete', 'validate', 'parse', 'format', 'load', 'save', 'get', 'set', 'send', 'test', 'usage', 'help'}


def ramp(x, lo, hi):
    return max(0.0, min(1.0, (x - lo) / float(hi - lo)))


def lead_ws(s):
    return s[:len(s) - len(s.lstrip(' \t'))]


def is_comment(s, lang):
    t = s.lstrip()
    if lang == 'py':
        return t.startswith('#')
    return t.startswith('//') or t.startswith('*') or t.startswith('/*') or (lang == 'other' and t.startswith('#'))


def list_files(root):
    """Paths relative to root. Uses git when root is in a repository (tracked + untracked-not-ignored), else walks."""
    tracked = None
    try:
        a = subprocess.run(['git', '-C', root, 'ls-files', '-z', '--cached'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=120)
        b = subprocess.run(['git', '-C', root, 'ls-files', '-z', '--others', '--exclude-standard'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=120)
        if a.returncode == 0 and b.returncode == 0:
            tracked = set(f for f in a.stdout.decode('utf8', 'replace').split('\0') if f)
            files = sorted(tracked | set(f for f in b.stdout.decode('utf8', 'replace').split('\0') if f))
    except Exception:
        tracked = None
    if tracked is None:
        files = []
        for d, dirs, names in os.walk(root):
            dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
            for n in names:
                files.append(os.path.relpath(os.path.join(d, n), root))
        files.sort()
    files = [f for f in files if not (set(f.split('/')[:-1]) & SKIP_DIRS) and os.path.isfile(os.path.join(root, f))]
    return files, tracked


def read_text(path):
    try:
        if os.path.getsize(path) > MAX_BYTES:
            return None
        with open(path, 'rb') as fh:
            raw = fh.read()
    except OSError:
        return None
    if b'\0' in raw[:8000]:
        return None
    return raw.decode('utf8', 'replace')


def is_generated(rel, lines):
    if '.min.' in rel or rel.endswith('.pb.go') or rel.endswith('_generated.go') or rel.endswith('.d.ts'):
        return True
    head = '\n'.join(lines[:6])
    if re.search(r'Code generated|DO NOT EDIT|@generated|autogenerated', head):
        return True
    return bool(lines) and sum(len(l) for l in lines) / float(len(lines)) > 300


def backtick_state(lines, lang):
    """True for lines that START inside a backtick string (JS template literal, Go raw string)."""
    st, inside = [], False
    for l in lines:
        st.append(inside)
        if not inside and is_comment(l, lang):
            continue
        if len(re.findall(r'(?<!\\)`', l)) % 2:
            inside = not inside
    return [False] * len(lines) if inside else st      # odd number in the file: the parity is not to be trusted


def code_part(s):
    return re.sub(r'\s+//.*$', '', s.strip())


def brace_end(lines, i, tpl):
    """Last line of the block that starts on line i: the next line at the SAME indentation that starts with '}'."""
    lead, s = lead_ws(lines[i]), code_part(lines[i])
    o, c = s.count('{'), s.count('}')
    cont = bool(re.search(r'(\(|,|=>|=|&&|\|\||\+|:)$', s)) or s.count('(') > s.count(')')
    if o and o == c and not cont:
        return i
    if not o and not cont:
        return i
    opened = o > c
    for j in range(i + 1, len(lines)):
        if tpl[j]:
            continue
        ts = lines[j].strip()
        if not ts:
            continue
        if not opened:
            if '{' in ts:
                opened = True
            elif j - i > 15:
                return None
            continue
        if ts[0] == '}' and lead_ws(lines[j]) == lead:
            return j
    return None


def brace_functions(lang, lines):
    tpl = backtick_state(lines, lang)
    out = []
    for i, raw in enumerate(lines):
        if tpl[i] or not raw.strip() or is_comment(raw, lang):
            continue
        name = kind = None
        if lang == 'go':
            m = GO_FUNC.match(raw)
            if m:
                name, kind = m.group(2), ('method' if m.group(1) else 'function')
        else:
            m = JS_HANDLER.match(raw)
            if m and re.search(r'=>|\bfunction\b', ' '.join(lines[i:i + 4])):
                name, kind = '%s %s' % (m.group(1).upper(), m.group(2)), 'handler'
            else:
                for rx, k in JS_FUNC:
                    m = rx.match(raw)
                    if m and (m.group(1) or '') not in JS_KW:
                        name, kind = m.group(1) or '(anonymous)', k
                        break
        if not name:
            continue
        end = brace_end(lines, i, tpl)
        if end is None:
            continue
        out.append({'name': name, 'kind': kind, 'start': i, 'end': end, 'top': kind == 'function' and not lead_ws(raw)})
    return out


def py_indent(s):
    e = s.expandtabs(8)
    return len(e) - len(e.lstrip())


def py_functions(lines):
    n, tq, inside = len(lines), [], False
    for l in lines:
        tq.append(inside)
        if (l.count('"""') + l.count("'''")) % 2:
            inside = not inside
    out = []
    for i, l in enumerate(lines):
        if tq[i]:
            continue
        m = PY_DEF.match(l)
        if not m:
            continue
        ind, bal, j = py_indent(l), 0, i
        while j < n and j - i <= 40:
            c = lines[j].split('#')[0]
            bal += sum(c.count(x) for x in '([{') - sum(c.count(x) for x in ')]}')
            if bal <= 0:
                break
            j += 1
        j = min(j, n - 1)
        end = j
        if not re.search(r':\s*\S', lines[j].split('#')[0][lines[j].rfind(')'):] if ')' in lines[j] else ''):
            for k in range(j + 1, n):
                if tq[k]:
                    end = k
                    continue
                if not lines[k].strip():
                    continue
                if py_indent(lines[k]) <= ind:
                    break
                end = k
        out.append({'name': m.group(2), 'kind': 'function' if ind == 0 else 'method', 'start': i, 'end': end, 'top': ind == 0})
    return out


def is_client(rel, text, ext):
    if ext in ('.jsx', '.tsx') or set(rel.split('/')[:-1]) & CLIENT_DIRS:
        return True
    return bool(re.search(r'\bdocument\.\w|\bwindow\.\w|from\s+[\'"]react[\'"]|require\([\'"]react[\'"]\)', text))


KEYS = 'root, tracked, F, src, tests, loc, kloc, fl, leftovers, secrets, secrets_in_tests, no_track'.split(', ')


def load(root):
    """Read the tree once: every code file with its lines and functions, plus what the file-name and secret scans found."""
    files, tracked = list_files(root)
    F = []                                    # per code file
    leftovers, secrets, secrets_in_tests, no_track = [], [], [], []
    for rel in files:
        ext = os.path.splitext(rel)[1].lower()
        base = os.path.basename(rel)
        if LEFTOVER_RE.search(base):
            leftovers.append(rel)
        if NO_TRACK_RE.search(rel):
            no_track.append(rel + ('' if tracked is None or rel in tracked else '  (untracked, but not ignored)'))
        if base in LOCKFILES:
            continue
        text = read_text(os.path.join(root, rel))
        if text is None:
            continue
        lines = text.split('\n')
        test = bool(TEST_RE.search(rel))
        for i, l in enumerate(lines):
            if len(l) > 2000:
                continue
            if KEY_HEADER.search(l) and i + 1 < len(lines) and re.match(r'^[A-Za-z0-9+/=]{40,}\s*$', lines[i + 1]):
                (secrets_in_tests if test else secrets).append('%s:%d  private key block' % (rel, i + 1))
                continue
            for label, rx in SECRET_PATTERNS:
                if rx.search(l) and not (label == 'hard-coded credential' and PLACEHOLDER_RE.search(l)):
                    (secrets_in_tests if test else secrets).append('%s:%d  %s' % (rel, i + 1, label))   # never the value
                    break
        lang = LANGS.get(ext) or ('other' if ext in OTHER_CODE else None)
        if not lang or is_generated(rel, lines) or LEFTOVER_RE.search(base):
            continue
        F.append({'rel': rel, 'ext': ext, 'lang': lang, 'lines': lines, 'text': text, 'test': test,
                  'client': lang == 'js' and is_client(rel, text, ext)})

    src = [f for f in F if not f['test']]
    tests = [f for f in F if f['test']]
    for f in src:
        f['loc'] = sum(1 for l in f['lines'] if l.strip())
        f['funcs'] = py_functions(f['lines']) if f['lang'] == 'py' else brace_functions(f['lang'], f['lines']) if f['lang'] in ('js', 'go') else []
    loc = sum(f['loc'] for f in src) or 1
    kloc = loc / 1000.0
    fl = [f for f in src if f['lang'] in LANGS.values()]
    return dict(zip(KEYS, (root, tracked, F, src, tests, loc, kloc, fl, leftovers, secrets, secrets_in_tests, no_track)))


def m_monolith(add, src, loc, **_):
    # monolith files
    big = sorted(src, key=lambda f: -len(f['lines']))
    largest = len(big[0]['lines']) if big else 0
    over = [f for f in big if len(f['lines']) > 1000]
    share = sum(f['loc'] for f in over) / float(loc)
    add('monolith', 'Separation of concerns: add nothing to a monolith file', 12, bool(src),
        0.6 * ramp(largest, 500, 3000) + 0.4 * ramp(share, 0, 0.5),
        'largest file %d lines; %d file(s) over 1,000 lines hold %d%% of the code' % (largest, len(over), round(share * 100)),
        ['%s  %d lines' % (f['rel'], len(f['lines'])) for f in big[:5] if len(f['lines']) > 500])


def m_long_functions(add, fl, **_):
    # long functions
    allf = [(fn['end'] - fn['start'] + 1, f['rel'], fn) for f in fl for fn in f['funcs']]
    long150 = sorted([x for x in allf if x[0] > 150], key=lambda x: -x[0])
    n300 = sum(1 for x in long150 if x[0] > 300)
    # a long function inside a long function is counted once: take the outermost
    weight_lines = 0
    for f in fl:
        spans = sorted([(fn['start'], fn['end']) for fn in f['funcs'] if fn['end'] - fn['start'] + 1 > 150])
        last = -1
        for a, b in spans:
            if a > last:
                weight_lines += (b - a + 1) * (2 if b - a + 1 > 300 else 1)
                last = b
    fl_lines = sum(len(f['lines']) for f in fl) or 1
    add('long_functions', 'Single responsibility: no function or handler over 150 lines', 14, bool(fl),
        ramp(weight_lines / float(fl_lines), 0, 0.25),
        '%d over 150 lines, %d of them over 300 (of %d functions found)' % (len(long150), n300, len(allf)),
        ['%s:%d  %s  %d lines' % (rel, fn['start'] + 1, fn['name'], n) for n, rel, fn in long150[:5]])


def m_inner_imports(add, src, **_):
    # imports inside functions
    hits = Counter()
    il = [f for f in src if f['lang'] in INNER_IMPORT]
    for f in il:
        inside = [False] * len(f['lines'])
        for fn in f['funcs']:
            for k in range(fn['start'] + 1, fn['end'] + 1):
                inside[k] = True
        rx = INNER_IMPORT[f['lang']]
        for i, l in enumerate(f['lines']):
            if inside[i] and not is_comment(l, f['lang']) and rx.search(l):
                hits[f['rel']] += 1
    n = sum(hits.values())
    add('inner_imports', 'One owner per domain: a function-level import dodges a cycle', 6, bool(il),
        ramp(n / (sum(f['loc'] for f in il) / 1000.0 or 1), 0, 10), '%d import(s) inside functions in %d file(s)' % (n, len(hits)),
        ['%s  %d' % x for x in hits.most_common(5)], 'not applicable to Go' if not il else '')


def m_db_in_http(add, src, **_):
    # database calls in the HTTP layer
    http = [f for f in src if f['lang'] in HTTP_FILE and not f['client'] and HTTP_FILE[f['lang']].search(f['text'])]
    hits = Counter()
    for f in http:
        rx = DB_CALL[f['lang']]
        c = sum(1 for l in f['lines'] if not is_comment(l, f['lang']) and rx.search(l))
        if c:
            hits[f['rel']] = c
    n = sum(hits.values())
    add('db_in_http', 'No business logic in HTTP: a route parses, calls an owner, writes the result', 14, bool(http),
        ramp(n / (sum(f['loc'] for f in src if f['lang'] in HTTP_FILE and not f['client']) / 1000.0 or 1), 0, 10), '%d database call(s) in %d of %d HTTP-layer file(s)' % (n, len(hits), len(http)),
        ['%s  %d' % x for x in hits.most_common(5)], '' if http else 'no HTTP layer found')


def m_html_in_server(add, src, **_):
    # HTML built in server code
    server = [f for f in src if f['lang'] in LANGS.values() and not f['client']]
    hits = Counter()
    for f in server:
        c = sum(1 for l in f['lines'] if not is_comment(l, f['lang']) and HTML_RE.search(l))
        if c:
            hits[f['rel']] = c
    n = sum(hits.values())
    add('html_in_server', 'No business logic in rendering: HTML built inside server-side code', 6, bool(server),
        ramp(n / (sum(f['loc'] for f in server) / 1000.0 or 1), 0, 5), '%d line(s) of HTML in %d server-side file(s)' % (n, len(hits)),
        ['%s  %d' % x for x in hits.most_common(5)])


def m_repeats(add, src, kloc, **_):
    # repeats: identical lines four or more times, and identical six-line blocks
    W = 6
    linecount, where = Counter(), {}
    win = defaultdict(list)
    sig_total = 0
    per_file_sig = {}
    for f in src:
        sig = []
        for i, l in enumerate(f['lines']):
            t = ' '.join(l.split())
            if not t or is_comment(l, f['lang']) or IMPORT_LINE.match(t):
                continue
            sig.append((i, t))
            if len(t) >= 40:
                linecount[t] += 1
                where.setdefault(t, '%s:%d' % (f['rel'], i + 1))
        per_file_sig[f['rel']] = sig
        sig_total += len(sig)
        for k in range(len(sig) - W + 1):
            w = [t for _, t in sig[k:k + W]]
            if sum(len(t) for t in w) < 180 or sum(1 for t in w if len(t) >= 20) < 4:
                continue
            h = hashlib.md5('\n'.join(w).encode('utf8', 'replace')).digest()
            if len(win[h]) < 3:
                win[h].append((f['rel'], k))
            else:
                win[h][2] = (win[h][2][0], -1)       # marker only: seen more than twice
    dup_keys = {h: v for h, v in win.items() if len(v) >= 2}
    covered = defaultdict(set)
    example = {}
    for f in src:
        sig = per_file_sig[f['rel']]
        for k in range(len(sig) - W + 1):
            w = [t for _, t in sig[k:k + W]]
            if sum(len(t) for t in w) < 180:
                continue
            h = hashlib.md5('\n'.join(w).encode('utf8', 'replace')).digest()
            v = dup_keys.get(h)
            if not v:
                continue
            covered[f['rel']].update(range(k, k + W))
            if f['rel'] not in example:
                twin = next(((r, kk) for r, kk in v if kk >= 0 and (r, kk) != (f['rel'], k)), None)
                if twin:
                    example[f['rel']] = '%s:%d = %s:%d' % (f['rel'], sig[k][0] + 1, twin[0], per_file_sig[twin[0]][twin[1]][0] + 1)
    dup_lines = sum(len(v) for v in covered.values())
    dup_share = dup_lines / float(sig_total or 1)
    rep = [(c, t) for t, c in linecount.items() if c >= 4]
    rep.sort(key=lambda x: -x[0])
    excess = sum(c - 1 for c, _ in rep)
    offenders = ['%s' % example.get(r, r) + '  (%d duplicated lines in this file)' % len(v) for r, v in sorted(covered.items(), key=lambda x: -len(x[1]))[:4]]
    offenders += ['x%d  %s  %s' % (c, where[t], t[:70]) for c, t in rep[:4]]
    add('repeats', 'Never duplicate logic: one home for every rule, threshold and format string', 14, bool(src),
        0.7 * ramp(dup_share, 0, 0.15) + 0.3 * ramp(excess / kloc, 0, 20),
        '%d%% of code lines sit in a block that exists twice; %d distinct line(s) repeated 4+ times' % (round(dup_share * 100), len(rep)), offenders)


def m_same_name(add, fl, **_):
    # the same function name defined in several files
    names = defaultdict(set)
    ntop = 0
    for f in fl:
        for fn in f['funcs']:
            if fn['top'] and len(fn['name']) >= 5 and fn['name'].lower() not in GENERIC_NAMES and fn['name'] != '(anonymous)':
                names[fn['name']].add(f['rel'])
                ntop += 1
    multi = sorted([(len(v), k, sorted(v)) for k, v in names.items() if len(v) >= 2], key=lambda x: (-x[0], x[1]))
    add('same_name', 'Never duplicate logic: a function that re-implements one that exists', 6, bool(fl),
        ramp(len(multi) / (ntop / 100.0 or 1), 0, 10), '%d function name(s) defined in two or more files (of %d top-level functions)' % (len(multi), ntop),
        ['%s  in %d files: %s' % (k, n, ', '.join(v[:3]) + (' …' if n > 3 else '')) for n, k, v in multi[:6]], 'candidates: read them before calling them copies')


def m_leftovers(add, leftovers, **_):
    # leftovers
    add('leftovers', 'Optimize for deletion: leftover .bak / .orig / copy files', 4, True, ramp(len(leftovers), 0, 5),
        '%d leftover file(s)' % len(leftovers), leftovers[:6])


def m_swallowed_errors(add, src, **_):
    # swallowed errors
    hits = Counter()
    sl = [f for f in src if f['lang'] in SWALLOW]
    for f in sl:
        rx, ls = SWALLOW[f['lang']], f['lines']
        c = 0
        for i, l in enumerate(ls):
            if is_comment(l, f['lang']):
                continue
            if rx.search(l):
                c += 1
            elif f['lang'] == 'js' and re.search(r'\bcatch\s*(\([^)]*\))?\s*\{\s*$', l) and i + 1 < len(ls) and ls[i + 1].strip().startswith('}'):
                c += 1
            elif f['lang'] == 'py' and re.match(r'^\s*except\b[^:]*:\s*$', l) and i + 1 < len(ls) and ls[i + 1].strip() in ('pass', '...'):
                c += 1
        if c:
            hits[f['rel']] = c
    n = sum(hits.values())
    add('swallowed_errors', 'Fail fast, and fail closed: errors caught and dropped', 6, bool(sl),
        ramp(n / (sum(f['loc'] for f in sl) / 1000.0 or 1), 0, 3), '%d swallowed error(s) in %d file(s)' % (n, len(hits)),
        ['%s  %d' % x for x in hits.most_common(5)], 'check whether any sits on an authorization path: there an error must refuse')


def m_secrets(add, secrets, secrets_in_tests, no_track, **_):
    # secrets
    found = secrets + ['%s  must never be tracked' % x for x in no_track]
    sure = [x for x in found if not re.search(r'Google API key|hard-coded credential', x)]
    add('secrets', 'Secrets never enter git', 8, True, 1.0 if sure else 0.5 if found else 0.0,
        '%d possible secret(s) or secret file(s)' % len(found) + (' (+%d in test files, not scored)' % len(secrets_in_tests) if secrets_in_tests else ''),
        found[:8] + ['%s  (test file: check it is a fixture)' % s for s in secrets_in_tests[:3]], 'history is not scanned: a secret removed from the tree still needs rotating')


def m_gates(add, root, src, tests, **_):
    # gates
    tops = [root]
    try:
        t = subprocess.run(['git', '-C', root, 'rev-parse', '--show-toplevel'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=20)
        if t.returncode == 0 and t.stdout.strip():
            tops.append(t.stdout.decode().strip())
    except Exception:
        pass
    ci = lint = False
    blob = ''
    for top in tops:
        for p in ('.github/workflows', '.gitlab-ci.yml', '.circleci', 'Jenkinsfile', 'azure-pipelines.yml', 'scripts/gates.sh', 'gates.sh', '.pre-commit-config.yaml', '.husky'):
            ci = ci or os.path.exists(os.path.join(top, p))
        for p in ('.eslintrc', '.eslintrc.js', '.eslintrc.cjs', '.eslintrc.json', '.eslintrc.yml', 'eslint.config.js', 'eslint.config.mjs', 'eslint.config.cjs',
                  'biome.json', '.golangci.yml', '.golangci.yaml', 'ruff.toml', '.ruff.toml', '.flake8', '.pylintrc'):
            lint = lint or os.path.exists(os.path.join(top, p))
        cand = ['Makefile', 'package.json', 'pyproject.toml', 'setup.cfg', 'scripts/gates.sh', 'gates.sh']
        wf = os.path.join(top, '.github/workflows')
        if os.path.isdir(wf):
            cand += ['.github/workflows/' + x for x in os.listdir(wf)]
        for p in cand:
            blob += read_text(os.path.join(top, p)) or ''
    ci = ci or bool(re.search(r'^(test|check|gates?):', blob, re.M))
    lint = lint or bool(re.search(r'golangci-lint|go vet|staticcheck|eslint|\bruff\b|flake8|pylint|biome (check|lint)|\btsc\b|mypy', blob))
    ratio = len(tests) / float(len(src) or 1)
    missing = [x for x, ok in (('tests', ratio > 0), ('a CI or gate script', ci), ('a lint', lint)) if not ok]
    add('gates', 'Gates, not promises: tests, a lint and one script that runs them', 6, bool(src),
        0.5 * (1 - ramp(ratio, 0, 0.1)) + 0.25 * (not ci) + 0.25 * (not lint),
        '%d test file(s) for %d source file(s); CI or gate script: %s; lint: %s' % (len(tests), len(src), 'yes' if ci else 'NO', 'yes' if lint else 'NO'),
        ['missing: ' + ', '.join(missing)] if missing else [])


def m_exemptions(add, F, tests, kloc, **_):
    # exemptions
    hits = Counter()
    for f in F:
        c = sum(1 for l in f['lines'] if EXEMPT_RE.search(l))
        if c:
            hits[f['rel']] = c
    n = sum(hits.values())
    add('exemptions', 'No exemptions: lint switched off, checks skipped, tests skipped', 4, bool(F),
        ramp(n / kloc, 0, 2), '%d suppression(s) or skipped test(s) in %d file(s)' % (n, len(hits)), ['%s  %d' % x for x in hits.most_common(5)])


MEASURES = [m_monolith, m_long_functions, m_inner_imports, m_db_in_http, m_html_in_server, m_repeats, m_same_name, m_leftovers, m_swallowed_errors, m_secrets, m_gates, m_exemptions]


def measure(root):
    c = load(root)
    root, tracked, F, src, tests, loc, kloc, fl, leftovers, secrets, secrets_in_tests, no_track = (c[k] for k in KEYS)
    M = []

    def add(key, rule, weight, applicable, frac, found, offenders, note=''):
        M.append({'key': key, 'rule': rule, 'weight': weight, 'applicable': applicable,
                  'points': round(weight * frac, 1) if applicable else 0.0, 'found': found, 'offenders': offenders[:8], 'note': note})

    for m in MEASURES:
        m(add, **c)
    possible = sum(m['weight'] for m in M if m['applicable']) or 1
    score = int(round(100.0 * sum(m['points'] for m in M) / possible))
    grade = next(g for lim, g in ((10, 'A  clean'), (25, 'B  mostly clean'), (45, 'C  some slop'), (65, 'D  sloppy'), (101, 'F  slop')) if score <= lim)
    langs = Counter(f['lang'] if f['lang'] != 'other' else f['ext'] for f in src)
    return {'root': os.path.abspath(root), 'score': score, 'grade': grade, 'code_lines': loc if src else 0, 'source_files': len(src), 'test_files': len(tests),
            'languages': dict(langs), 'file_level_only': sorted(set(f['ext'] for f in src if f['lang'] == 'other')),
            'file_list': 'git (tracked + untracked, not ignored)' if tracked is not None else 'directory walk (not a git repository)', 'measures': M}


def report(r):
    out = ['SLOP SCORE  %d / 100   grade %s' % (r['score'], r['grade']),
           '%s' % r['root'],
           '%s code lines in %d source files (%s), %d test files; file list: %s' % (
               format(r['code_lines'], ','), r['source_files'], ', '.join('%s %d' % x for x in sorted(r['languages'].items(), key=lambda x: -x[1])) or 'none',
               r['test_files'], r['file_list'])]
    if r['file_level_only']:
        out.append('file-level measures only for: ' + ' '.join(r['file_level_only']))
    out += ['', '%-6s %-7s  %s' % ('points', 'of', 'rule'), '-' * 100]
    for m in sorted(r['measures'], key=lambda m: -m['points']):
        out.append('%-6s %-7s  %s' % (('%.1f' % m['points']) if m['applicable'] else 'n/a', m['weight'], m['rule']))
        out.append('%-15s  %s%s' % ('', m['found'], ('   [' + m['note'] + ']') if m['note'] else ''))
        for o in m['offenders']:
            out.append('%-15s    %s' % ('', o))
    return '\n'.join(out)


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if len(args) != 1 or not os.path.isdir(args[0]):
        sys.stderr.write('usage: measure.py <directory> [--json]\n')
        sys.exit(2)
    result = measure(args[0])
    print(json.dumps(result, indent=1) if '--json' in sys.argv else report(result))
