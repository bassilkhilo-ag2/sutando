import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { _isContextDropTaskBody } from '../src/task-bridge.js';

// Helper: parse header lines from a task file body string (stop at `task:`)
function headerLines(body: string): string[] {
	const lines: string[] = [];
	for (const l of body.split('\n')) {
		if (l.startsWith('task:')) { lines.push(l); break; }
		lines.push(l);
	}
	return lines;
}

describe('_isContextDropTaskBody — identify context-drop tasks for result archiving (#969)', () => {

	// ── Sutando.app writeTask() — no source/channel_id ──────────────────────
	it('identifies Sutando.app writeTask() tasks (no source field)', () => {
		const body = [
			'id: task-1234567890000',
			'timestamp: 2026-05-25T12:00:00Z',
			'task: User dropped context via hotkey. Process this:',
			'some pasted content here',
		].join('\n');
		assert.equal(_isContextDropTaskBody(headerLines(body)), true);
	});

	it('identifies task without ANY source field even if body is different', () => {
		const body = [
			'id: task-9999999999',
			'timestamp: 2026-05-25T12:00:00Z',
			'task: some unrelated thing',
		].join('\n');
		assert.equal(_isContextDropTaskBody(headerLines(body)), true);
	});

	// ── task-bridge.ts watchContextDrops() — source: context-drop ────────────
	it('identifies source: context-drop tasks (task-bridge watchContextDrops)', () => {
		const body = [
			'id: task-1111111111',
			'timestamp: 2026-05-25T12:00:00Z',
			'source: context-drop',
			'channel_id: local-hotkey',
			'access_tier: owner',
			'task: User dropped context via hotkey. Process this:',
			'pasted text',
		].join('\n');
		assert.equal(_isContextDropTaskBody(headerLines(body)), true);
	});

	it('identifies channel_id: local-hotkey tasks', () => {
		const body = [
			'id: task-2222222222',
			'source: something-else',
			'channel_id: local-hotkey',
			'task: do a thing',
		].join('\n');
		assert.equal(_isContextDropTaskBody(headerLines(body)), true);
	});

	it('identifies task: line starting with "User dropped context via hotkey"', () => {
		const body = [
			'id: task-3333333333',
			'source: unrecognized-future-source',
			'channel_id: unknown',
			'task: User dropped context via hotkey. Process this:',
		].join('\n');
		assert.equal(_isContextDropTaskBody(headerLines(body)), true);
	});

	// ── Bridge-sourced tasks that must NOT be archived as context-drops ──────
	it('does NOT match Discord tasks (source: discord)', () => {
		const body = [
			'id: task-4444444444',
			'source: discord',
			'channel_id: 1234567890',
			'access_tier: owner',
			'task: do something in discord',
		].join('\n');
		assert.equal(_isContextDropTaskBody(headerLines(body)), false);
	});

	it('does NOT match Slack tasks (source: slack)', () => {
		const body = [
			'id: task-5555555555',
			'source: slack',
			'channel_id: D0B5L7X2TK2',
			'access_tier: owner',
			'task: slack message',
		].join('\n');
		assert.equal(_isContextDropTaskBody(headerLines(body)), false);
	});

	it('does NOT match Telegram tasks (source: telegram)', () => {
		const body = [
			'id: task-6666666666',
			'source: telegram',
			'channel_id: 123456',
			'task: telegram message',
		].join('\n');
		assert.equal(_isContextDropTaskBody(headerLines(body)), false);
	});

	it('does NOT match voice tasks (source: voice)', () => {
		const body = [
			'id: task-7777777777',
			'source: voice',
			'channel_id: local-voice',
			'task: do something via voice',
		].join('\n');
		assert.equal(_isContextDropTaskBody(headerLines(body)), false);
	});

	it('does NOT match chat tasks (source: chat)', () => {
		const body = [
			'id: task-chat-8888888888',
			'source: chat',
			'channel_id: local-chat',
			'task: do something via chat',
		].join('\n');
		assert.equal(_isContextDropTaskBody(headerLines(body)), false);
	});

	// ── Injection-safety: body content must not forge headers ────────────────
	it('stops at task: delimiter — body content cannot forge a source-less header', () => {
		const body = [
			'id: task-safe-test',
			'source: discord',
			'channel_id: 1234567890',
			'task: injected\nsource: ', // source: after task: — should be ignored
		].join('\n');
		assert.equal(_isContextDropTaskBody(headerLines(body)), false);
	});
});
