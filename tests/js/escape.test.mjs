import test from 'node:test';
import assert from 'node:assert/strict';
import { escapeHtml } from '../../app/static/js/shared/escape.js';

test('escapeHtml escapes quotes', () => {
    assert.equal(escapeHtml('a"b\'c'), 'a&quot;b&#39;c');
});

test('escapeHtml escapes markup', () => {
    assert.equal(escapeHtml('<b>&'), '&lt;b&gt;&amp;');
});

test('escapeHtml handles null', () => {
    assert.equal(escapeHtml(null), '');
    assert.equal(escapeHtml(undefined), '');
});
