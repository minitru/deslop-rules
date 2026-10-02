// The shape of the HTTP layer, as a gate: a route handler parses, calls an owner and answers; an owner takes plain
// values and never touches the request or response. Written for Express; adapt the two patterns for your framework.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');

const SRC = path.join(__dirname, '../src');
const js = (dir) => (fs.existsSync(path.join(SRC, dir)) ? fs.readdirSync(path.join(SRC, dir)).filter((f) => f.endsWith('.js')).map((f) => path.join(dir, f)) : []);

const MAX_HANDLER_LINES = 150;
test(`no route handler is longer than ${MAX_HANDLER_LINES} lines`, () => {
    const long = [];
    for (const rel of ['server.js', ...js('routes')]) {
        const lines = fs.readFileSync(path.join(SRC, rel), 'utf8').split('\n');
        let start = null; let head = '';
        lines.forEach((l, i) => {
            if (/^(app|router)\.(get|post|put|delete|patch)\(/.test(l)) { start = i; head = l.slice(0, 70); }
            else if (start !== null && l.startsWith('});')) { const n = i - start + 1; if (n > MAX_HANDLER_LINES) long.push(`${n} ${rel} ${head}`); start = null; }
        });
    }
    // Note: this only sees handlers registered at column 0. A handler defined inside another function is invisible —
    // which is itself a finding.
    assert.deepEqual(long, [], 'move the body to an owner module');
});

// Modules that still read the request or write the response. This list may only SHRINK: when a module stops, the
// second assertion fails until you take it off.
const LEGACY = [];
test('owners do not read req or write res (the legacy list only shrinks)', () => {
    const touches = [...js('services'), ...js('utils')].filter((rel) =>
        /(^|[^\w.])req\.(body|query|params|headers|user|ip)\b|(^|[^\w.])res\.(status|json|send)\(/m.test(fs.readFileSync(path.join(SRC, rel), 'utf8')));
    assert.deepEqual(touches.filter((f) => !LEGACY.includes(f)), [], 'a service takes plain values and returns {status, body}');
    assert.deepEqual(LEGACY.filter((f) => !touches.includes(f)), [], 'this module no longer touches req/res — take it off LEGACY');
});
