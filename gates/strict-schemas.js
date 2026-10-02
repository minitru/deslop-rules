// Preloaded for every test process (NODE_OPTIONS='--require ./gates/strict-schemas.js').
// Mongoose's default is to silently DROP a write to a field the schema does not declare. In tests, make it throw:
// fields that were "written" for months and never stored show up the first time a test touches them.
// Production keeps the default.
try { require('mongoose').set('strict', 'throw'); } catch (_) { /* not a Mongoose project: adapt for your ORM */ }
