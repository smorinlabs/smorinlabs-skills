/* Optional DOM smoke test against any generated map (no live sources).
 * npm install --prefix /tmp/session-map-dom linkedom@0.18.12
 * NODE_PATH=/tmp/session-map-dom/node_modules node tests/session_map_dom.cjs /path/to/index.html
 * A real browser is still needed for visual layout and clipboard permissions.
 */
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const {parseHTML} = require('linkedom');
const html = fs.readFileSync(process.argv[2], 'utf8');
const {window, document} = parseHTML(html);
const data = JSON.parse(document.getElementById('inventory').textContent);
const source = [...document.querySelectorAll('script')].find(s => !s.id).textContent;
let copied = null, exported = false;
for (const id of ['search', 'manager', 'agent']) {
  Object.defineProperty(document.getElementById(id), 'value', {value: '', writable: true});
}
const location = {hash: '#overview'};
const context = vm.createContext({document, window, location, console, Blob,
  navigator: {clipboard: {writeText: async text => {copied = text;}}},
  URL: {createObjectURL: () => {exported = true; return 'blob:test';}, revokeObjectURL: () => {}},
  setTimeout: fn => fn()});
vm.runInContext(source, context, {timeout: 10000});
function visit(hash) {
  location.hash = hash;
  window.dispatchEvent(new window.Event('hashchange'));
  assert(document.getElementById('view').textContent.length > 0);
}
function click(id) { document.getElementById(id).dispatchEvent(new window.Event('click', {bubbles: true})); }
for (const route of ['overview','projects','sessions','closure','history','changes','sources']) visit('#'+route);
for (const id of Object.keys(data.projects)) visit('#project/'+encodeURIComponent(id));
for (const id of Object.keys(data.locations)) visit('#session/'+encodeURIComponent(id));
for (const id of Object.keys(data.plans).slice(0, 10)) visit('#plan/'+encodeURIComponent(id));
visit('#sessions');
document.getElementById('search').value = 'no-such-session-needle-73aa';
document.getElementById('search').dispatchEvent(new window.Event('input'));
assert.equal(document.querySelectorAll('#view article.card').length, 0);
document.getElementById('search').value = '';
document.getElementById('search').dispatchEvent(new window.Event('input'));
const target = Object.values(data.locations).find(r => r.navigation);
if (target) {
  visit('#session/'+encodeURIComponent(target.id));
  const buttons = [...document.querySelectorAll('#view button[data-copy]')];
  const button = buttons.find(b => b.getAttribute('data-copy') === target.navigation.command);
  assert(button, 'exact terminal command missing');
  button.dispatchEvent(new window.Event('click', {bubbles: true}));
  assert.equal(copied, target.navigation.command);
}
click('update'); assert.equal(copied, data.render.update_prompt);
click('render'); assert.equal(copied, data.render.render_command);
click('export'); assert(exported);
assert.equal(document.querySelectorAll('script[src],link[rel=stylesheet]').length, 0);
console.log(JSON.stringify({projects: Object.keys(data.projects).length,
  locations: Object.keys(data.locations).length, navigation: !!target, routes: 7, result: 'pass'}));
