import { describe, it, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdirSync, readFileSync, rmSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

// Set SUTANDO_WORKSPACE to an isolated tmp dir before importing event_log.ts
// so tests don't write to the real workspace.
const TMP_WS = join(tmpdir(), `sutando-event-log-test-${Date.now()}`);
process.env.SUTANDO_WORKSPACE = TMP_WS;
mkdirSync(join(TMP_WS, 'logs'), { recursive: true });

// Import AFTER setting env var so resolveWorkspace() picks up the override.
const { logEvent } = await import('../src/event_log.js');

function todayStr(): string {
	return new Date().toISOString().slice(0, 10);
}
function logPath(): string {
	return join(TMP_WS, 'logs', `events-${todayStr()}.jsonl`);
}
function readLines(): Array<Record<string, unknown>> {
	const raw = readFileSync(logPath(), 'utf-8').trim();
	return raw.split('\n').filter(Boolean).map(l => JSON.parse(l));
}

describe('event_log.ts — structured event JSONL writer', () => {

	after(() => {
		try { rmSync(TMP_WS, { recursive: true }); } catch { /* ignore */ }
	});

	it('writes an event file to logs/events-YYYY-MM-DD.jsonl', () => {
		logEvent('meta.test');
		assert.ok(existsSync(logPath()), 'log file should exist after first write');
	});

	it('emits required fields: ts, node, kind', () => {
		logEvent('test.fields', { foo: 'bar' });
		const lines = readLines();
		const last = lines[lines.length - 1];
		assert.ok(typeof last.ts === 'number', 'ts should be a number');
		assert.ok(last.ts > 0, 'ts should be a positive unix timestamp');
		assert.ok(typeof last.node === 'string', 'node should be a string');
		assert.ok(last.node.length > 0, 'node should not be empty');
		assert.equal(last.kind, 'test.fields');
	});

	it('includes extra fields from the fields argument', () => {
		logEvent('test.extra', { taskId: 'task-123', source: 'voice', snippet: 'hello world' });
		const lines = readLines();
		const last = lines[lines.length - 1];
		assert.equal(last.taskId, 'task-123');
		assert.equal(last.source, 'voice');
		assert.equal(last.snippet, 'hello world');
	});

	it('each call appends a new line (multiple events per file)', () => {
		const before = readLines().length;
		logEvent('test.append.1');
		logEvent('test.append.2');
		logEvent('test.append.3');
		const after = readLines().length;
		assert.equal(after - before, 3);
	});

	it('does not throw on undefined/null field values', () => {
		assert.doesNotThrow(() => {
			logEvent('test.null-fields', { a: null, b: undefined });
		});
	});

	it('is non-fatal when workspace is unwritable (no throw)', () => {
		// Temporarily override SUTANDO_WORKSPACE to a read-only path.
		const orig = process.env.SUTANDO_WORKSPACE;
		process.env.SUTANDO_WORKSPACE = '/nonexistent-path-that-cannot-be-written';
		assert.doesNotThrow(() => logEvent('test.unwritable'));
		process.env.SUTANDO_WORKSPACE = orig;
	});

	it('date partition: file name matches today YYYY-MM-DD', () => {
		const name = `events-${todayStr()}.jsonl`;
		assert.ok(existsSync(join(TMP_WS, 'logs', name)), `expected ${name} to exist`);
	});
});
