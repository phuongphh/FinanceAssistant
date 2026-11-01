const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
test('maintenance branches have one operator publisher and keep ordinary CI', () => {
  const workflow=fs.readFileSync('.github/workflows/auto-pr.yml','utf8');
  assert.match(workflow, /!codex\/maintenance-\*/);
  assert.match(fs.readFileSync('.github/workflows/ci.yml','utf8'), /pull_request:/);
  assert.match(fs.readFileSync('.github/workflows/code-review.yml','utf8'), /pull_request:/);
});
