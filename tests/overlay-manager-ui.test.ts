/**
 * Unit tests for src/overlay-manager-ui.ts — OVERLAY_MANAGER_HTML constant.
 *
 * The export is a raw HTML string; tests verify structure and key UI content
 * rather than rendering behaviour.
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { OVERLAY_MANAGER_HTML } from '../src/overlay-manager-ui.ts';

// ---------------------------------------------------------------------------
// Basic export shape
// ---------------------------------------------------------------------------

test('OVERLAY_MANAGER_HTML is a non-empty string', () => {
	assert.equal(typeof OVERLAY_MANAGER_HTML, 'string');
	assert.ok(OVERLAY_MANAGER_HTML.length > 0);
});

test('OVERLAY_MANAGER_HTML starts with DOCTYPE declaration', () => {
	assert.ok(
		OVERLAY_MANAGER_HTML.trimStart().startsWith('<!DOCTYPE html>'),
		'Should begin with <!DOCTYPE html>',
	);
});

test('OVERLAY_MANAGER_HTML contains <html> and <body> tags', () => {
	assert.ok(OVERLAY_MANAGER_HTML.includes('<html'), 'Missing <html>');
	assert.ok(OVERLAY_MANAGER_HTML.includes('<body'), 'Missing <body>');
	assert.ok(OVERLAY_MANAGER_HTML.includes('</html>'), 'Missing </html>');
	assert.ok(OVERLAY_MANAGER_HTML.includes('</body>'), 'Missing </body>');
});

// ---------------------------------------------------------------------------
// Title and heading
// ---------------------------------------------------------------------------

test('page title is "Sutando — Overlay Manager"', () => {
	assert.ok(
		OVERLAY_MANAGER_HTML.includes('<title>Sutando — Overlay Manager</title>'),
		'Expected page title not found',
	);
});

test('page h1 is "Overlay Manager"', () => {
	assert.ok(
		OVERLAY_MANAGER_HTML.includes('Overlay Manager'),
		'Expected h1 text not found',
	);
});

// ---------------------------------------------------------------------------
// Key DOM elements
// ---------------------------------------------------------------------------

test('contains a #list element', () => {
	assert.ok(OVERLAY_MANAGER_HTML.includes('id="list"'), 'Missing #list element');
});

test('contains a #status element', () => {
	assert.ok(OVERLAY_MANAGER_HTML.includes('id="status"'), 'Missing #status element');
});

test('contains a refresh button', () => {
	assert.ok(OVERLAY_MANAGER_HTML.includes('id="refresh"'), 'Missing #refresh button');
});

// ---------------------------------------------------------------------------
// Overlay card controls
// ---------------------------------------------------------------------------

test('card() builds Open/Close/Show/Hide buttons', () => {
	assert.ok(OVERLAY_MANAGER_HTML.includes('"open"'), 'Missing open action');
	assert.ok(OVERLAY_MANAGER_HTML.includes('"close"'), 'Missing close action');
	assert.ok(OVERLAY_MANAGER_HTML.includes('"show"'), 'Missing show action');
	assert.ok(OVERLAY_MANAGER_HTML.includes('"hide"'), 'Missing hide action');
});

test('config section includes opacity range input', () => {
	assert.ok(OVERLAY_MANAGER_HTML.includes('type="range"'), 'Missing range input');
	assert.ok(OVERLAY_MANAGER_HTML.includes('opacity'), 'Missing opacity config');
});

test('config section includes alwaysOnTop checkbox', () => {
	assert.ok(OVERLAY_MANAGER_HTML.includes('alwaysOnTop'), 'Missing alwaysOnTop config');
	assert.ok(OVERLAY_MANAGER_HTML.includes('type="checkbox"'), 'Missing checkbox input');
});

// ---------------------------------------------------------------------------
// JavaScript API client
// ---------------------------------------------------------------------------

test('script uses /api/overlays endpoint', () => {
	assert.ok(
		OVERLAY_MANAGER_HTML.includes("'/api/overlays'"),
		'Expected /api/overlays prefix in fetch call',
	);
});

test('script defines load() and card() functions', () => {
	assert.ok(OVERLAY_MANAGER_HTML.includes('async function load()'), 'Missing load()');
	assert.ok(OVERLAY_MANAGER_HTML.includes('function card('), 'Missing card()');
});

test('script sets up 5-second auto-refresh interval', () => {
	assert.ok(OVERLAY_MANAGER_HTML.includes('setInterval(load, 5000)'), 'Missing 5s poll');
});

test('script attaches click listener to refresh button', () => {
	assert.ok(
		OVERLAY_MANAGER_HTML.includes("getElementById('refresh')"),
		'Missing refresh click listener',
	);
});

// ---------------------------------------------------------------------------
// Badge states
// ---------------------------------------------------------------------------

test('badge styles include open, closed, hidden states', () => {
	assert.ok(OVERLAY_MANAGER_HTML.includes('.badge.open'), 'Missing .badge.open');
	assert.ok(OVERLAY_MANAGER_HTML.includes('.badge.closed'), 'Missing .badge.closed');
	assert.ok(OVERLAY_MANAGER_HTML.includes('.badge.hidden'), 'Missing .badge.hidden');
});
