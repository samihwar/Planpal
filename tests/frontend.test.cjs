// Run with: node --test tests/frontend.test.cjs
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'frontend/app.js'), 'utf8');

class Element {
  constructor(tag = 'input') {
    this.tag = tag;
    this.children = [];
    this._value = '';
    this.dataset = {};
    this.style = {};
    this.listeners = {};
    this.classes = new Set();
    this.classList = {
      contains: name => this.classes.has(name),
      add: name => this.classes.add(name),
      remove: name => this.classes.delete(name),
      toggle: (name, on) => on ? this.classes.add(name) : this.classes.delete(name),
    };
  }
  get value() { return this._value; }
  set value(value) {
    this._value = this.tag === 'select' && !this.children.some(o => o.value === String(value)) ? '' : String(value);
  }
  set innerHTML(value) { this.children = []; }
  get options() { return this.children; }
  append(...nodes) { this.children.push(...nodes); }
  querySelector(selector) {
    const value = selector.match(/option\[value="(.*)"\]/)?.[1];
    return this.children.find(o => o.value === value) || null;
  }
  querySelectorAll(selector) {
    return this.children.filter(o => selector.split(',').map(s => s.trim()).includes(o.tag));
  }
  closest() { return null; }
  scrollIntoView() {}
  setAttribute() {}
  addEventListener(name, listener) { this.listeners[name] = listener; }
}

function harness() {
  const elements = new Map();
  const selects = ['#parsed-time-input', '#parsed-duration-input', '#parsed-project-input'];
  const context = vm.createContext({
    window: { location: { origin: 'http://localhost', hostname: 'localhost' }, setTimeout() {} },
    document: {
      querySelector: selector => {
        if (!elements.has(selector)) elements.set(selector, new Element(selects.includes(selector) ? 'select' : 'input'));
        return elements.get(selector);
      },
      createElement: tag => new Element(tag),
      addEventListener() {},
    },
    localStorage: { getItem: () => null, setItem() {} },
    CSS: { escape: value => value },
    navigator: {},
    console,
  });
  vm.runInContext(source, context);
  const run = code => vm.runInContext(code, context);
  run(`
    initializeTimeOptions();
    for (const value of ['', 'all_day', '15', '30', '45', '60', '90', '120']) {
      elements.durationInput.append(timeOption(value, value));
    }
  `);
  return { context, elements, run };
}

test('opening and saving an event preserves a non-preset duration', () => {
  const { run } = harness();
  run(`openEditTask({id:'one', title:'Meeting', date:'2026-09-05', time:'23:15', duration:3.25, project:'Work'});`);
  assert.equal(run('elements.durationInput.value'), '195');
  assert.equal(run('taskFromReview().duration'), 3.25);
  assert.equal(run('taskFromReview().project'), 'Work');
});

test('a goal can be completed, then unchecked in Archive to return to active goals', async () => {
  const { run, context } = harness();
  let saved = {id:'one', title:'Review goal', completed:false, archived:false};
  context.fetch = async (url, options = {}) => {
    if (options.method === 'PATCH') saved = {...saved, ...JSON.parse(options.body)};
    return {ok:true, json:async () => ({tasks:[saved]})};
  };
  run('renderTasks = () => {};');
  await run('loadTasks({quiet:true})');
  run(`let card = renderTaskCard(tasks[0]); let checkbox = card.children[0]; checkbox.checked = true;`);
  await run(`checkbox.listeners.change()`);
  assert.equal(saved.completed, true);
  assert.equal(run('groupTasks(tasks).archive.length'), 1);

  run(`card = renderTaskCard(tasks[0], {archivedView:true}); checkbox = card.children[0];`);
  assert.equal(run('Boolean(checkbox.disabled)'), false);
  assert.equal(run('checkbox.checked'), true);
  run('checkbox.checked = false;');
  await run('checkbox.listeners.change()');
  assert.equal(saved.completed, false);
  assert.equal(saved.archived, false);
  assert.equal(run('groupTasks(tasks).archive.length'), 0);
  assert.equal(run('groupTasks(tasks).tasks.length'), 1);
});

test('a failed undo leaves the saved goal completed in Archive', async () => {
  const { run, context } = harness();
  run(`tasks = [normalizeTask({id:'one', title:'Review goal', completed:true, archived:true})]; renderTasks = () => {}; const checkbox = renderTaskCard(tasks[0], {archivedView:true}).children[0]; checkbox.checked = false;`);
  context.fetch = async () => ({ok:false, json:async () => ({detail:'Could not update task'})});
  await run('checkbox.listeners.change()');
  assert.equal(run('groupTasks(tasks).archive[0].completed'), true);
  assert.equal(run('elements.errorMessage.textContent'), 'Could not update task');
});

test('time follow-up dropdown values are submitted, including no time', () => {
  const { run } = harness();
  run(`const select = document.createElement('select'); select.name = 'time'; populateTimeSelect(select); elements.followUpFields.append(select); select.value = '09:15';`);
  assert.equal(run('collectFollowUpAnswers().time'), '09:15');
  run(`select.value = NO_TIME_VALUE;`);
  assert.equal(run('collectFollowUpAnswers().time'), '__no_time__');
});

test('clearing the time field clears the saved value', () => {
  const { run } = harness();
  run(`openEditTask({id:'one', title:'Meeting', date:'2026-09-05', time:'09:15'}); elements.manualTimeInput.value = ''; handleManualTimeInput();`);
  assert.equal(run('taskFromReview().time'), null);
  assert.equal(run('elements.confirmButton.disabled'), true);
});

test('sync preserves the selected project and unsaved color', async () => {
  const { run, context } = harness();
  run(`openEditTask({id:'one', title:'Meeting', project:'Work'}); elements.projectColorInput.value = '#112233'; renderTasks = () => {};`);
  context.fetch = async () => ({ok:true, json:async () => ({tasks:[]})});
  await run('loadTasks({quiet:true})');
  assert.equal(run('elements.projectInput.value'), 'Work');
  assert.equal(run('elements.projectColorInput.value'), '#112233');
});

test('failed deletion keeps the edit panel and pending task', async () => {
  const { run, context } = harness();
  run(`openEditTask({id:'one', title:'Meeting', project:'Work'});`);
  context.fetch = async () => ({ok:false, json:async () => ({detail:'Offline'})});
  await run('handleApplyDetails()');
  assert.equal(run('pendingTask.id'), 'one');
  assert.equal(run(`elements.reviewPanel.classList.contains('hidden')`), false);
  assert.equal(run('isBusy'), false);
});

test('blocked local storage does not prevent saving a task', async () => {
  const { run, context } = harness();
  run(`openEditTask({id:'one', title:'Meeting', project:'Work'}); loadTasks = async () => {};`);
  context.localStorage.setItem = () => { throw new Error('Storage unavailable'); };
  let saved = false;
  context.fetch = async () => { saved = true; return {ok:true, json:async () => ({})}; };
  await run('handleConfirm()');
  assert.equal(saved, true);
  assert.equal(run('pendingTask'), null);
});

test('keyboard parse shortcut cannot start a second request while busy', async () => {
  const { run, context } = harness();
  run(`isBusy = true; elements.taskInput.value = 'Meeting';`);
  context.fetch = () => { throw new Error('Should not request'); };
  await run('handleParse()');
});

test('validation errors show readable messages', () => {
  const { run } = harness();
  assert.equal(run(`apiErrorMessage({detail:[{msg:'A task title is required'}]}, 'Failed')`), 'A task title is required');
});

test('plain-text server errors produce a readable message instead of a JSON parsing error', async () => {
  const { run, context } = harness();
  context.fetch = async () => ({status:500, ok:false, json:async () => { throw new SyntaxError('Unexpected token I'); }});
  await run('loadTasks({quiet:true})');
  assert.match(run('elements.errorMessage.textContent'), /HTTP 500/);
  assert.doesNotMatch(run('elements.errorMessage.textContent'), /SyntaxError|Unexpected token/);
});

test('overnight event is split accurately and midnight end creates no extra day', () => {
  const { run } = harness();
  assert.equal(run(`JSON.stringify(calendarOccurrencesForTask({date:'2026-09-05', time:'23:15', duration:3.25}).map(o => [o.dateKey, o.item.occurrence_duration]))`),
    JSON.stringify([['2026-09-05', 0.75], ['2026-09-06', 2.5]]));
  assert.equal(run(`calendarOccurrencesForTask({date:'2026-09-05', time:'23:00', duration:1}).length`), 1);
});

test('service worker precaches the versions referenced by the page', () => {
  const sw = fs.readFileSync(path.join(root, 'frontend/sw.js'), 'utf8');
  const html = fs.readFileSync(path.join(root, 'frontend/index.html'), 'utf8');
  for (const asset of html.match(/\/(?:app\.js|style\.css)\?v=[^" ]+/g)) {
    assert.ok(sw.includes(`"${asset}"`), `${asset} missing from precache`);
  }
});

test('service worker leaves API, external and non-GET requests alone', () => {
  const handlers = {};
  vm.runInNewContext(fs.readFileSync(path.join(root, 'frontend/sw.js'), 'utf8'), {
    URL,
    self: {location:{origin:'http://localhost'}, addEventListener:(name, fn) => handlers[name] = fn},
  });
  for (const request of [
    {url:'http://localhost/api/tasks', method:'GET'},
    {url:'http://localhost/health', method:'GET'},
    {url:'https://fonts.googleapis.com/css', method:'GET'},
    {url:'http://localhost/something', method:'POST'},
  ]) {
    handlers.fetch({request, respondWith:() => assert.fail('Should not intercept')});
  }
});
