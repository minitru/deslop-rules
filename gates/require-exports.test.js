// Every name a file destructures out of a local require() must be something that module exports.
//
// Why: code-moving tools (and people) rebuild import lines. `const { signPayload: sign } = require('./signer')`
// rewritten as `const { sign } = require('./signer')` is valid JavaScript, a declared name, and undefined.
// An undefined-name lint passes, the app boots, and the first call throws "sign is not a function".
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');

const SRC = path.join(__dirname, '../src');
const SKIP = new Set(['server.js']);          // modules that start the server (or have other side effects) when loaded

function walk(dir, out = []) {
    for (const f of fs.readdirSync(dir)) {
        const p = path.join(dir, f);
        if (fs.statSync(p).isDirectory()) walk(p, out); else if (f.endsWith('.js')) out.push(p);
    }
    return out;
}

test('destructured require names exist in the module they come from', () => {
    const missing = [];
    const RE = /(?:const|let|var)\s*\{([^}]*)\}\s*=\s*require\(\s*['"](\.{1,2}\/[^'"]+)['"]\s*\)/g;
    for (const file of walk(SRC)) {
        const text = fs.readFileSync(file, 'utf8');
        let m;
        while ((m = RE.exec(text))) {
            const target = path.resolve(path.dirname(file), m[2]);
            if (SKIP.has(path.relative(SRC, target).replace(/\.js$/, '') + '.js')) continue;
            let mod;
            try { mod = require(target); } catch (_) { continue; }     // a module that cannot load is the boot check's business
            if (!mod || (typeof mod !== 'object' && typeof mod !== 'function')) continue;
            for (const part of m[1].split(',')) {
                const t = part.replace(/\/\/.*$/gm, '').trim();
                if (!t || t.startsWith('...') || t.includes('=')) continue;   // rest element, or a default value
                const key = t.split(':')[0].trim();
                if (!(key in mod)) missing.push(`${path.relative(SRC, file)}: { ${t} } from '${m[2]}' is not exported`);
            }
        }
    }
    assert.deepEqual(missing, []);
});
