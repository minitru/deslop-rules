// boot-check.js — load the server the way production does, and exit the moment it would bind its port.
// A syntax check and a test suite both pass while a deployed server crash-loops on a ReferenceError at module
// load (an import below its first use, a name that was never required). This sees that.
// Caveat: anything your app defines INSIDE its listen() callback never runs here. Keep that callback to
// startup-only work (timers, checks); routes and helpers belong at module scope.
const http = require('http');
http.Server.prototype.listen = function () { console.log('BOOT OK (listen intercepted)'); process.exit(0); };
setTimeout(() => { console.error('BOOT TIMEOUT: the server did not reach listen() in 60s'); process.exit(1); }, 60000).unref();
process.on('uncaughtException', (e) => { console.error('BOOT FAILED:', (e && e.stack) || e); process.exit(1); });
require('../src/server.js');   // <- your entry point
