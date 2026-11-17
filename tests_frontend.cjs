const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function initialize(hasForm, loadingLabel = 'Saving answer…', valid = true) {
  const documentEvents = {};
  const windowEvents = {};
  const formEvents = {};
  const inputEvents = {};
  const attributes = {};
  const button = { disabled: false, innerHTML: 'Submit answer →' };
  const input = { style: {}, scrollHeight: 340, addEventListener: (name, handler) => { inputEvents[name] = handler; } };
  const form = {
    dataset: { loadingLabel },
    checkValidity: () => valid,
    reportValidity: () => { attributes.validationReported = true; },
    querySelector: () => button,
    addEventListener: (name, handler) => { formEvents[name] = handler; },
    setAttribute: (name, value) => { attributes[name] = value; },
    removeAttribute: (name) => { delete attributes[name]; },
  };
  const context = {
    document: {
      querySelector: (selector) => hasForm && selector === '#answer' ? input : null,
      querySelectorAll: () => hasForm ? [form] : [],
      addEventListener: (name, handler) => { documentEvents[name] = handler; },
    },
    window: { addEventListener: (name, handler) => { windowEvents[name] = handler; } },
  };
  vm.runInNewContext(fs.readFileSync('static/js/script.js', 'utf8'), context);
  documentEvents.DOMContentLoaded();
  return { windowEvents, formEvents, inputEvents, attributes, button, input };
}

const page = initialize(true);
page.inputEvents.input();
assert.equal(page.input.style.height, '340px');
let prevented = false;
page.formEvents.submit({ preventDefault: () => { prevented = true; } });
assert.equal(prevented, false);
assert.equal(page.button.disabled, true);
assert.equal(page.button.textContent, 'Saving answer…');
assert.equal(page.attributes['aria-busy'], 'true');
page.formEvents.submit({ preventDefault: () => { prevented = true; } });
assert.equal(prevented, true);
page.windowEvents.pageshow();
assert.equal(page.button.disabled, false);
assert.equal(page.attributes['aria-busy'], undefined);
assert.equal(page.button.innerHTML, 'Submit answer →');
for (const label of ['Preparing questions...', 'Logging in...', 'Creating profile...']) {
  const pending = initialize(true, label);
  pending.formEvents.submit({ preventDefault: () => assert.fail('Valid form was blocked') });
  assert.equal(pending.button.textContent, label);
  assert.equal(pending.button.disabled, true);
  pending.windowEvents.pageshow();
  assert.equal(pending.button.disabled, false);
}
const invalid = initialize(true, 'Preparing questions...', false);
let invalidPrevented = false;
invalid.formEvents.submit({ preventDefault: () => { invalidPrevented = true; } });
assert.equal(invalidPrevented, true);
assert.equal(invalid.button.disabled, false);
assert.equal(invalid.attributes.validationReported, true);
initialize(false);

// Exercise the actual domain picker and per-question drafts using keyed elements.
const callbacks = {};
const category = { value: 'technical', addEventListener: (event, callback) => { callbacks[event] = callback; } };
const domain = {};
const domainField = {};
const drafts = new Map([['interview-1-question-2', 'Unsubmitted draft']]);
const answer = { dataset: { draftKey: 'interview-1-question-2' }, value: '', readOnly: false,
  style: {}, scrollHeight: 100, addEventListener: (event, callback) => { callbacks.answerInput = callback; } };
const elements = { '#category': category, '#domain': domain, '#domain-field': domainField, '#answer': answer };
const ui = {
  document: { querySelector: (selector) => elements[selector], querySelectorAll: () => [],
    addEventListener: (event, callback) => { callbacks.ready = callback; } },
  window: { addEventListener: (event, callback) => { callbacks.pageShow = callback; },
    sessionStorage: { getItem: (key) => drafts.get(key), setItem: (key, value) => drafts.set(key, value), removeItem: (key) => drafts.delete(key) } },
};
vm.runInNewContext(fs.readFileSync('static/js/script.js', 'utf8'), ui);
callbacks.ready();
assert.equal(domain.required, true);
assert.equal(domain.disabled, false);
assert.equal(domainField.hidden, false);
category.value = 'hr';
callbacks.change();
assert.equal(domainField.hidden, true);
assert.equal(domain.disabled, true);
assert.equal(domain.required, false);
category.value = 'technical';
callbacks.pageShow();
assert.equal(domain.disabled, false);
assert.equal(answer.value, 'Unsubmitted draft');
answer.value = 'Updated draft';
callbacks.answerInput();
assert.equal(drafts.get(answer.dataset.draftKey), 'Updated draft');
answer.readOnly = true;
answer.value = 'Server-saved answer';
callbacks.ready();
assert.equal(answer.value, 'Server-saved answer');
assert.equal(drafts.has(answer.dataset.draftKey), false);
console.log('Frontend checks passed: domain picker, draft restoration, loading states, validation, duplicate guard, Back restoration, resize, pages without forms.');
