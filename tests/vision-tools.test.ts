/**
 * Unit tests for src/vision-tools.ts.
 *
 * Pure-function tests: source registry, contributor registry, tool-updater
 * wiring, initial streaming state, tool metadata.
 *
 * Execute-path tests: only paths that do NOT call fetch/execFile/screencapture
 * are covered:
 *   - No-session early exits (startVisionTool, sendVisionFrameTool, startStreaming)
 *   - stopVisionTool when idle (always safe)
 *   - Push-mode paths: startStreaming('browser') with a mock session that has
 *     sendFile but no sendContent — no network, no OS call. sendFile-only mock
 *     causes the screen-share-started injection block to be skipped (checked
 *     via `typeof transport.sendContent === 'function'` which is false).
 *
 * All tests clean up module-scope state via setVisionSession(null) /
 * stopStreaming() in finally blocks.
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
	registerSource,
	listSources,
	registerVisionOnContributor,
	_getVisionOnContributorCount,
	setVisionSession,
	setSessionToolUpdater,
	callUpdateTools,
	callRestoreTools,
	getFullToolSurface,
	isStreaming,
	getVisionState,
	startStreaming,
	stopStreaming,
	submitFrame,
	sendVisionFrameTool,
	startVisionTool,
	stopVisionTool,
} from '../src/vision-tools.ts';

import type { ToolDefinition } from 'bodhi-realtime-agent';

type AnyRecord = Record<string, unknown>;

/** Minimal mock session: just enough for getSendFile() to return non-null. */
function makeMockSession(opts: { sendContent?: boolean } = {}) {
	const transport: Record<string, unknown> = {
		sendFile: () => {},
		isConnected: true,
	};
	if (opts.sendContent) {
		transport.sendContent = () => {};
	}
	return { transport };
}

// ---------------------------------------------------------------------------
// Source registry — pure
// ---------------------------------------------------------------------------

test('listSources includes built-in screen and webcam', () => {
	const names = listSources();
	assert.ok(names.includes('screen'), 'Expected "screen" in sources');
	assert.ok(names.includes('webcam'), 'Expected "webcam" in sources');
});

test('registerSource adds a new source that appears in listSources', () => {
	const before = listSources().length;
	registerSource({ name: 'test-cam', async capture() { return { data: Buffer.alloc(0), mimeType: 'image/jpeg' }; } });
	const after = listSources();
	assert.ok(after.includes('test-cam'), 'Expected "test-cam" after register');
	assert.equal(after.length, before + 1);
});

test('registerSource is case-insensitive (name lowercased in registry)', () => {
	registerSource({ name: 'Glasses', async capture() { return { data: Buffer.alloc(0), mimeType: 'image/jpeg' }; } });
	assert.ok(listSources().includes('glasses'), 'Expected "glasses" (lowercase) in sources');
});

// ---------------------------------------------------------------------------
// VisionOnContributor registry
// ---------------------------------------------------------------------------

test('_getVisionOnContributorCount returns a non-negative integer', () => {
	const count = _getVisionOnContributorCount();
	assert.equal(typeof count, 'number');
	assert.ok(count >= 0);
});

test('registerVisionOnContributor increments count by 1', () => {
	const before = _getVisionOnContributorCount();
	const unregister = registerVisionOnContributor(() => 'test contribution');
	try {
		assert.equal(_getVisionOnContributorCount(), before + 1);
	} finally {
		unregister();
	}
});

test('unregister function returned by registerVisionOnContributor removes the contributor', () => {
	const before = _getVisionOnContributorCount();
	const unregister = registerVisionOnContributor(() => 'will be removed');
	unregister();
	assert.equal(_getVisionOnContributorCount(), before, 'Count should return to baseline after unregister');
});

// ---------------------------------------------------------------------------
// Tool-updater wiring
// ---------------------------------------------------------------------------

test('getFullToolSurface returns an array', () => {
	assert.ok(Array.isArray(getFullToolSurface()));
});

test('callUpdateTools returns false when no updater is set', () => {
	setSessionToolUpdater(null, []);
	try {
		assert.equal(callUpdateTools([]), false);
	} finally {
		setSessionToolUpdater(null, []);
	}
});

test('callRestoreTools returns false when no updater is set', () => {
	setSessionToolUpdater(null, []);
	try {
		assert.equal(callRestoreTools(), false);
	} finally {
		setSessionToolUpdater(null, []);
	}
});

test('setSessionToolUpdater stores the full tool surface', () => {
	const fakeTool = { name: 'fake_tool' } as ToolDefinition;
	setSessionToolUpdater(() => {}, [fakeTool]);
	try {
		const surface = getFullToolSurface();
		assert.equal(surface.length, 1);
		assert.equal(surface[0].name, 'fake_tool');
	} finally {
		setSessionToolUpdater(null, []);
	}
});

test('callUpdateTools invokes the registered updater and returns true', () => {
	let received: ToolDefinition[] | null = null;
	setSessionToolUpdater((tools) => { received = tools; }, []);
	try {
		const result = callUpdateTools([]);
		assert.equal(result, true);
		assert.ok(Array.isArray(received));
	} finally {
		setSessionToolUpdater(null, []);
	}
});

test('callRestoreTools calls updater with the full tool surface', () => {
	const fakeTool = { name: 'work' } as ToolDefinition;
	let received: ToolDefinition[] | null = null;
	setSessionToolUpdater((tools) => { received = tools; }, [fakeTool]);
	try {
		const result = callRestoreTools();
		assert.equal(result, true);
		assert.ok(Array.isArray(received));
		assert.equal((received as ToolDefinition[])[0].name, 'work');
	} finally {
		setSessionToolUpdater(null, []);
	}
});

test('callRestoreTools returns false when fullToolSurface is empty', () => {
	setSessionToolUpdater(() => {}, []);
	try {
		assert.equal(callRestoreTools(), false);
	} finally {
		setSessionToolUpdater(null, []);
	}
});

// ---------------------------------------------------------------------------
// Streaming state — no session
// ---------------------------------------------------------------------------

test('isStreaming is false when no stream is running', () => {
	setVisionSession(null);
	assert.equal(isStreaming(), false);
});

test('getVisionState reflects non-streaming state with no session', () => {
	setVisionSession(null);
	const state = getVisionState();
	assert.equal(state.streaming, false);
	assert.equal(state.sessionReady, false);
	assert.equal(state.frames, 0);
});

// ---------------------------------------------------------------------------
// Tool metadata
// ---------------------------------------------------------------------------

test('sendVisionFrameTool has name send_vision_frame and execution inline', () => {
	assert.equal(sendVisionFrameTool.name, 'send_vision_frame');
	assert.equal(sendVisionFrameTool.execution, 'inline');
});

test('startVisionTool has name start_vision and execution inline', () => {
	assert.equal(startVisionTool.name, 'start_vision');
	assert.equal(startVisionTool.execution, 'inline');
});

test('stopVisionTool has name stop_vision and execution inline', () => {
	assert.equal(stopVisionTool.name, 'stop_vision');
	assert.equal(stopVisionTool.execution, 'inline');
});

test('startVisionTool description mentions streaming and fps', () => {
	const d = startVisionTool.description.toLowerCase();
	assert.ok(d.includes('stream'), `Expected "stream" in description`);
	assert.ok(d.includes('fps'), `Expected "fps" in description`);
});

test('stopVisionTool description mentions stop and stream', () => {
	const d = stopVisionTool.description.toLowerCase();
	assert.ok(d.includes('stop'), `Expected "stop" in description`);
	assert.ok(d.includes('stream') || d.includes('vision'), `Expected "stream/vision" in description`);
});

// ---------------------------------------------------------------------------
// Execute paths — no session (no OS/network calls)
// ---------------------------------------------------------------------------

test('stopVisionTool.execute returns idle when no stream is running', async () => {
	setVisionSession(null);
	const result = await (stopVisionTool.execute as () => Promise<AnyRecord>)();
	assert.equal(result.status, 'idle');
	assert.ok((result.note as string).toLowerCase().includes('not streaming'), `Expected "not streaming" in note: ${result.note}`);
});

test('startVisionTool.execute returns failed when no session is connected', async () => {
	setVisionSession(null);
	const result = await (startVisionTool.execute as (a: AnyRecord) => Promise<AnyRecord>)({});
	assert.equal(result.status, 'failed');
	assert.ok((result.error as string).toLowerCase().includes('session'), `Expected "session" in error: ${result.error}`);
});

test('startStreaming returns failed when no session is connected', () => {
	setVisionSession(null);
	const result = startStreaming('screen', 1, 'pull');
	assert.equal(result.status, 'failed');
	assert.ok('error' in result);
});

test('sendVisionFrameTool.execute returns failed when no session (not in pushMode)', async () => {
	setVisionSession(null);
	const result = await (sendVisionFrameTool.execute as (a: AnyRecord) => Promise<AnyRecord>)({});
	assert.ok('status' in result && result.status === 'failed', `Expected failed, got: ${JSON.stringify(result)}`);
});

test('submitFrame returns error when no active session', () => {
	setVisionSession(null);
	const result = submitFrame(Buffer.from('x'));
	assert.equal(result.ok, false);
	assert.ok((result.error as string).includes('no active voice session'), `Expected "no active voice session": ${result.error}`);
});

// ---------------------------------------------------------------------------
// Execute paths — with mock session, no push mode
// ---------------------------------------------------------------------------

test('setVisionSession with mock leaves isStreaming as false', () => {
	setVisionSession(makeMockSession());
	try {
		assert.equal(isStreaming(), false);
	} finally {
		setVisionSession(null);
	}
});

test('submitFrame returns not-in-push-mode error when push mode is inactive', () => {
	setVisionSession(makeMockSession());
	try {
		const result = submitFrame(Buffer.from('test'));
		assert.equal(result.ok, false);
		assert.ok((result.error as string).includes('push mode'), `Expected "push mode" in error: ${result.error}`);
	} finally {
		setVisionSession(null);
	}
});

test('stopStreaming returns idle when no stream is running', () => {
	setVisionSession(makeMockSession());
	try {
		const result = stopStreaming();
		assert.equal(result.status, 'idle');
	} finally {
		setVisionSession(null);
	}
});

test('getVisionState reports sessionReady true when session has sendFile', () => {
	setVisionSession(makeMockSession());
	try {
		const state = getVisionState();
		assert.equal(state.sessionReady, true);
		assert.equal(state.streaming, false);
	} finally {
		setVisionSession(null);
	}
});

// ---------------------------------------------------------------------------
// Push mode paths — mock session, no sendContent (skips injection block)
// ---------------------------------------------------------------------------

test('startStreaming returns streaming status when source is "browser" (push mode)', () => {
	setVisionSession(makeMockSession());
	try {
		const result = startStreaming('browser', undefined);
		assert.equal(result.status, 'streaming');
		assert.ok('mode' in result && result.mode === 'push', `Expected mode=push: ${JSON.stringify(result)}`);
	} finally {
		stopStreaming();
		setVisionSession(null);
	}
});

test('isStreaming returns true after push mode is started', () => {
	setVisionSession(makeMockSession());
	try {
		startStreaming('browser', undefined);
		assert.equal(isStreaming(), true);
	} finally {
		stopStreaming();
		setVisionSession(null);
	}
});

test('submitFrame succeeds when push mode is active and session is connected', () => {
	setVisionSession(makeMockSession());
	try {
		startStreaming('browser', undefined);
		const result = submitFrame(Buffer.from('fake-jpeg-bytes'), 'image/jpeg');
		assert.equal(result.ok, true);
	} finally {
		stopStreaming();
		setVisionSession(null);
	}
});

test('sendVisionFrameTool.execute returns push-mode note when pushMode is active', async () => {
	setVisionSession(makeMockSession());
	try {
		startStreaming('browser', undefined);
		const result = await (sendVisionFrameTool.execute as (a: AnyRecord) => Promise<AnyRecord>)({});
		assert.equal(result.status, 'sent');
		assert.ok(
			typeof result.note === 'string' && (result.note as string).includes('Push mode'),
			`Expected "Push mode" in note: ${result.note}`,
		);
	} finally {
		stopStreaming();
		setVisionSession(null);
	}
});

test('startVisionTool.execute returns streaming note when push mode already active', async () => {
	setVisionSession(makeMockSession());
	try {
		startStreaming('browser', undefined);
		const result = await (startVisionTool.execute as (a: AnyRecord) => Promise<AnyRecord>)({});
		assert.equal(result.status, 'streaming');
		assert.ok(
			typeof result.note === 'string' && (result.note as string).includes('Push mode'),
			`Expected "Push mode" in note: ${result.note}`,
		);
	} finally {
		stopStreaming();
		setVisionSession(null);
	}
});

test('stopStreaming returns stopped status after push mode was active', () => {
	setVisionSession(makeMockSession());
	startStreaming('browser', undefined);
	try {
		const result = stopStreaming();
		assert.equal(result.status, 'stopped');
	} finally {
		setVisionSession(null);
	}
});

test('isStreaming is false after stopStreaming is called', () => {
	setVisionSession(makeMockSession());
	startStreaming('browser', undefined);
	stopStreaming();
	setVisionSession(null);
	assert.equal(isStreaming(), false);
});
