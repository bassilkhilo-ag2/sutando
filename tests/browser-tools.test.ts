/**
 * Unit tests for src/browser-tools.ts.
 *
 * injectText: tested with mock session objects — no OS calls.
 *
 * Tool execute paths: only pre-execSync early-exit branches are tested so
 * no Chrome/AppleScript/osascript process is spawned during the test run.
 *
 * Specifically tested:
 *   openUrlTool   — empty URL, whitespace URL, zero-width-char URL
 *   clickTool     — no-args error path
 *   pointAtTool   — missing API key error, empty query error
 *
 * Happy paths (which call execSync/execFileSync/fetch) are intentionally
 * skipped to keep tests host-agnostic.
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
	injectText,
	scrollTool,
	switchTabTool,
	closeTabTool,
	openUrlTool,
	describeScreenTool,
	clickTool,
	pointAtTool,
} from '../src/browser-tools.ts';

type AnyRecord = Record<string, unknown>;

function clearGeminiEnv() {
	delete process.env.GEMINI_VOICE_API_KEY;
	delete process.env.GEMINI_API_KEY;
}

// ---------------------------------------------------------------------------
// Tool metadata
// ---------------------------------------------------------------------------

test('scrollTool has name scroll and execution inline', () => {
	assert.equal(scrollTool.name, 'scroll');
	assert.equal(scrollTool.execution, 'inline');
});

test('switchTabTool has name switch_tab and execution inline', () => {
	assert.equal(switchTabTool.name, 'switch_tab');
	assert.equal(switchTabTool.execution, 'inline');
});

test('closeTabTool has name close_tab and execution inline', () => {
	assert.equal(closeTabTool.name, 'close_tab');
	assert.equal(closeTabTool.execution, 'inline');
});

test('openUrlTool has name open_url and execution inline', () => {
	assert.equal(openUrlTool.name, 'open_url');
	assert.equal(openUrlTool.execution, 'inline');
});

test('openUrlTool description mentions reuse and new tab', () => {
	const d = openUrlTool.description.toLowerCase();
	assert.ok(d.includes('reuse') || d.includes('reuses'), 'Expected "reuse" in description');
	assert.ok(d.includes('new tab'), 'Expected "new tab" in description');
});

test('describeScreenTool has name describe_screen and execution inline', () => {
	assert.equal(describeScreenTool.name, 'describe_screen');
	assert.equal(describeScreenTool.execution, 'inline');
});

test('clickTool has name click and execution inline', () => {
	assert.equal(clickTool.name, 'click');
	assert.equal(clickTool.execution, 'inline');
});

test('pointAtTool has name point_at and execution inline', () => {
	assert.equal(pointAtTool.name, 'point_at');
	assert.equal(pointAtTool.execution, 'inline');
});

test('pointAtTool description mentions point and screen', () => {
	const d = pointAtTool.description.toLowerCase();
	assert.ok(d.includes('point'), 'Expected "point" in description');
	assert.ok(d.includes('screen'), 'Expected "screen" in description');
});

// ---------------------------------------------------------------------------
// injectText — mock session transport
// ---------------------------------------------------------------------------

test('injectText calls sendRealtimeInput when available', () => {
	let called: string | null = null;
	const session = {
		transport: {
			session: {
				sendRealtimeInput: (arg: { text: string }) => { called = arg.text; },
			},
		},
	};
	injectText(session, 'hello world');
	assert.equal(called, 'hello world');
});

test('injectText calls sendContent when sendRealtimeInput is absent', () => {
	let called: unknown = null;
	const session = {
		transport: {
			sendContent: (parts: unknown[], _end: boolean) => { called = parts; },
		},
	};
	injectText(session, 'test message');
	assert.ok(Array.isArray(called), 'Expected sendContent to be called with an array');
	assert.ok(
		JSON.stringify(called).includes('test message'),
		'Expected text in sendContent args',
	);
});

test('injectText does not throw when session is null', () => {
	assert.doesNotThrow(() => injectText(null, 'hi'));
});

test('injectText does not throw when transport has no send method', () => {
	const session = { transport: {} };
	assert.doesNotThrow(() => injectText(session, 'hi'));
});

// ---------------------------------------------------------------------------
// openUrlTool — pre-execSync validation paths
// ---------------------------------------------------------------------------

test('openUrlTool returns error for empty string URL', async () => {
	const result = await (openUrlTool.execute as (a: AnyRecord) => Promise<AnyRecord>)({ url: '' });
	assert.ok('error' in result, `Expected error, got: ${JSON.stringify(result)}`);
	assert.ok((result.error as string).includes('empty'), `Expected "empty" in error: ${result.error}`);
});

test('openUrlTool returns error for whitespace-only URL', async () => {
	const result = await (openUrlTool.execute as (a: AnyRecord) => Promise<AnyRecord>)({ url: '   ' });
	assert.ok('error' in result, `Expected error, got: ${JSON.stringify(result)}`);
	assert.ok((result.error as string).includes('empty'), `Expected "empty" in error: ${result.error}`);
});

test('openUrlTool returns error for URL with embedded space', async () => {
	const result = await (openUrlTool.execute as (a: AnyRecord) => Promise<AnyRecord>)({ url: 'https://example.com/path with spaces' });
	assert.ok('error' in result, `Expected error, got: ${JSON.stringify(result)}`);
	assert.ok((result.error as string).includes('whitespace'), `Expected "whitespace" in error: ${result.error}`);
});

test('openUrlTool returns error for URL with zero-width character', async () => {
	const result = await (openUrlTool.execute as (a: AnyRecord) => Promise<AnyRecord>)({ url: 'https://example.com/​path' });
	assert.ok('error' in result, `Expected error, got: ${JSON.stringify(result)}`);
	assert.ok((result.error as string).includes('zero-width'), `Expected "zero-width" in error: ${result.error}`);
});

test('openUrlTool returns error for URL with newline character', async () => {
	const result = await (openUrlTool.execute as (a: AnyRecord) => Promise<AnyRecord>)({ url: 'https://example.com/\npath' });
	assert.ok('error' in result, `Expected error, got: ${JSON.stringify(result)}`);
	assert.ok((result.error as string).includes('whitespace'), `Expected "whitespace" in error: ${result.error}`);
});

// ---------------------------------------------------------------------------
// clickTool — no-args path (pure error, no execSync)
// ---------------------------------------------------------------------------

test('clickTool returns error when neither coords nor shortcut provided', async () => {
	const result = await (clickTool.execute as (a: AnyRecord) => Promise<AnyRecord>)({});
	assert.ok('error' in result, `Expected error, got: ${JSON.stringify(result)}`);
	assert.ok(
		(result.error as string).includes('x,y') || (result.error as string).includes('coordinates'),
		`Expected coordinates hint in error: ${result.error}`,
	);
});

// ---------------------------------------------------------------------------
// pointAtTool — pre-fetch validation paths
// ---------------------------------------------------------------------------

test('pointAtTool returns error when no API key set', async () => {
	clearGeminiEnv();
	try {
		const result = await (pointAtTool.execute as (a: AnyRecord) => Promise<AnyRecord>)({ query: 'the commit button' });
		assert.ok('error' in result, `Expected error, got: ${JSON.stringify(result)}`);
		assert.ok(
			(result.error as string).includes('GEMINI'),
			`Expected GEMINI key mention in error: ${result.error}`,
		);
	} finally {
		clearGeminiEnv();
	}
});

test('pointAtTool returns error for empty query string', async () => {
	clearGeminiEnv();
	process.env.GEMINI_API_KEY = 'test-key-not-real';
	try {
		const result = await (pointAtTool.execute as (a: AnyRecord) => Promise<AnyRecord>)({ query: '   ' });
		assert.ok('error' in result, `Expected error, got: ${JSON.stringify(result)}`);
		assert.ok(
			(result.error as string).includes('query'),
			`Expected "query" in error: ${result.error}`,
		);
	} finally {
		clearGeminiEnv();
	}
});
