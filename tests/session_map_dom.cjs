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
let clearedPlanProject;
if (process.argv.includes('--null-plan')) {
  clearedPlanProject = Object.values(data.projects).find(p => p.plan_ids?.length);
  assert(clearedPlanProject, 'null-plan fixture needs a project plan');
  clearedPlanProject.assessment = {...clearedPlanProject.assessment,
    selected_plan: clearedPlanProject.plan_ids[0]};
  clearedPlanProject.overrides = {...clearedPlanProject.overrides, selected_plan: null};
}
if (process.argv.includes('--container')) {
  const child = Object.values(data.locations).find(r => r.navigation);
  assert(child, 'container fixture needs a navigable location');
  data.locations['location:container-fixture'] = {id: 'location:container-fixture',
    presence: 'observed', title: 'Container fixture', navigation: {command: 'fixture focus container'}};
  child.overrides = {...child.overrides, container_id: 'location:container-fixture'};
}
if (process.argv.includes('--adversarial')) {
  const plan = Object.values(data.plans).find(p => p.phases?.length);
  assert(plan, 'adversarial fixture needs a project plan');
  const phase = plan.phases[0];
  phase.counts = {...phase.counts, total: '1"><img id="session-map-injected-total">',
    complete: '<img id="session-map-injected-count">'};
  phase.tasks = [{id: 'P01-T01', state: 'open', title: 'Synthetic task',
    line: '<img id="session-map-injected-line">'}];
}
document.getElementById('inventory').textContent = JSON.stringify(data);
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
  assert(!document.querySelector('[id^="session-map-injected-"]'),
    'saved inventory text became an HTML element on '+hash);
}
function click(id) { document.getElementById(id).dispatchEvent(new window.Event('click', {bubbles: true})); }
for (const route of ['overview','projects','sessions','closure','history','changes','sources']) visit('#'+route);
for (const id of Object.keys(data.projects)) visit('#project/'+encodeURIComponent(id));
if (clearedPlanProject) {
  visit('#project/'+encodeURIComponent(clearedPlanProject.id));
  assert(document.getElementById('view').textContent.includes('No authoritative plan pinned.'),
    'explicit null correction did not clear the selected plan');
}
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
  const container = data.locations[target.overrides?.container_id];
  const expected = target.navigation.command + (container?.navigation && container.presence === 'observed'
    ? ' &&\n' + container.navigation.command : '');
  const button = buttons.find(b => b.getAttribute('data-copy') === expected);
  assert(button, 'exact terminal command missing');
  button.dispatchEvent(new window.Event('click', {bubbles: true}));
  assert.equal(copied, expected);
}
click('update'); assert.equal(copied, data.render.update_prompt);
click('render'); assert.equal(copied, data.render.render_command);
click('export'); assert(exported);
assert.equal(document.querySelectorAll('script[src],link[rel=stylesheet]').length, 0);
console.log(JSON.stringify({projects: Object.keys(data.projects).length,
  locations: Object.keys(data.locations).length, navigation: !!target, routes: 7, result: 'pass'}));
