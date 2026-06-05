/**
 * Unit tests for src/task-bridge.ts.
 *
 * _shouldFallthrough: pure function — no module needed, tested directly.
 *
 * workTool: metadata only (execute writes files + calls pgrep — too much
 * side-effect for a unit test without heavy mocking).
 *
 * readCurrentNoteViewing: reads from a fixed /tmp path — tested by writing
 * there directly and restoring afterward.
 *
 * File-I/O functions (writeChatTask, _isVoiceTask, logConversation,
 * getRecentConversation, getSecondsSinceLastTurn, logSessionBoundary):
 * SUTANDO_WORKSPACE is set to a temp dir before the cache-busted import so
 * the module-scope constants (TASK_DIR, RESULT_DIR, CONVERSATION_LOG) all
 * land in an isolated tree that gets cleaned up after each test.
 *
 * setInterval-based watchers (startResultWatcher, startContextDropWatcher,
 * startNoteViewingWatcher) are not invoked — no timers started in this suite.
 */

import assert from 'node:assert/strict';
import { mkdirSync, rmSync, writeFileSync, readFileSync, existsSync, unlinkSync } from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { test } from 'node:test';

import { _shouldFallthrough, workTool } from '../src/task-bridge.ts';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mkTmp(): { dir: string; cleanup: () => void } {
	const dir = join('/tmp', `tb-test-${Date.now()}-${Math.floor(Math.random() * 1e6)}`);
	mkdirSync(dir, { recursive: true });
	return { dir, cleanup: () => rmSync(dir, { recursive: true, force: true }) };
}

type BridgeModule = typeof import('../src/task-bridge.ts');

async function freshBridge(workspaceDir: string): Promise<BridgeModule> {
	const origWs = process.env.SUTANDO_WORKSPACE;
	process.env.SUTANDO_WORKSPACE = workspaceDir;
	try {
		const srcUrl = pathToFileURL(join(process.cwd(), 'src', 'task-bridge.ts')).href;
		return (await import(`${srcUrl}?t=${Date.now()}`)) as BridgeModule;
	} finally {
		if (origWs === undefined) delete process.env.SUTANDO_WORKSPACE;
		else process.env.SUTANDO_WORKSPACE = origWs;
	}
}

// ---------------------------------------------------------------------------
// _shouldFallthrough — pure function, no module required
// ---------------------------------------------------------------------------

test('_shouldFallthrough: task- prefix → true', () => {
	assert.equal(_shouldFallthrough('task-1234567890.txt'), true);
	assert.equal(_shouldFallthrough('task-.txt'), true);
});

test('_shouldFallthrough: voice- prefix → true', () => {
	assert.equal(_shouldFallthrough('voice-prompt-1234.txt'), true);
});

test('_shouldFallthrough: proactive- prefix → true', () => {
	assert.equal(_shouldFallthrough('proactive-result-abc-1234.txt'), true);
	assert.equal(_shouldFallthrough('proactive-timeout-xyz.txt'), true);
});

test('_shouldFallthrough: discord-voice.task- prefix → false', () => {
	assert.equal(_shouldFallthrough('discord-voice.task-1234.txt'), false);
});

test('_shouldFallthrough: phone.task- prefix → false', () => {
	assert.equal(_shouldFallthrough('phone.task-1234.txt'), false);
});

test('_shouldFallthrough: question- prefix → true (check-pending-questions.py voice delivery)', () => {
	assert.equal(_shouldFallthrough('question-1234567890.txt'), true);
});

test('_shouldFallthrough: insight- prefix → true (daily-insight.py voice delivery)', () => {
	assert.equal(_shouldFallthrough('insight-2026.txt'), true);
});

test('_shouldFallthrough: friction- prefix → true (friction-detector.py voice delivery)', () => {
	assert.equal(_shouldFallthrough('friction-2026.txt'), true);
});

test('_shouldFallthrough: briefing- prefix → true (morning-briefing skill voice delivery)', () => {
	assert.equal(_shouldFallthrough('briefing-morning.txt'), true);
});

test('_shouldFallthrough: empty string → false', () => {
	assert.equal(_shouldFallthrough(''), false);
});

// ---------------------------------------------------------------------------
// workTool — metadata only
// ---------------------------------------------------------------------------

test('workTool has name work and execution inline', () => {
	assert.equal(workTool.name, 'work');
	assert.equal(workTool.execution, 'inline');
});

test('workTool description mentions task and result', () => {
	const d = workTool.description.toLowerCase();
	assert.ok(d.includes('task') || d.includes('work'), `Expected task/work in description`);
	assert.ok(d.includes('result') || d.includes('ready'), `Expected result/ready in description`);
});

test('workTool has task parameter', () => {
	const schema = workTool.parameters;
	assert.ok(schema !== null && schema !== undefined, 'Expected parameters schema');
	const parsed = (schema as { parse: (x: unknown) => unknown }).parse({ task: 'hello' });
	assert.ok(parsed !== null);
});

// ---------------------------------------------------------------------------
// readCurrentNoteViewing — reads from fixed /tmp path
// ---------------------------------------------------------------------------

const NOTE_VIEWING_PATH = '/tmp/sutando-note-viewing.json';

test('readCurrentNoteViewing returns null when file is absent', async () => {
	// Use a fresh module to get the function (same as production)
	const { readCurrentNoteViewing } = await import('../src/task-bridge.ts');
	const orig = existsSync(NOTE_VIEWING_PATH) ? readFileSync(NOTE_VIEWING_PATH, 'utf-8') : null;
	try {
		if (existsSync(NOTE_VIEWING_PATH)) unlinkSync(NOTE_VIEWING_PATH);
		assert.equal(readCurrentNoteViewing(), null);
	} finally {
		if (orig !== null) writeFileSync(NOTE_VIEWING_PATH, orig);
	}
});

test('readCurrentNoteViewing returns parsed event when valid JSON is present', async () => {
	const { readCurrentNoteViewing } = await import('../src/task-bridge.ts');
	const orig = existsSync(NOTE_VIEWING_PATH) ? readFileSync(NOTE_VIEWING_PATH, 'utf-8') : null;
	try {
		const event = { slug: 'test-note', content: 'Note content here', ts: '2026-06-05T12:00:00.000Z' };
		writeFileSync(NOTE_VIEWING_PATH, JSON.stringify(event));
		const result = readCurrentNoteViewing();
		assert.ok(result !== null, 'Expected non-null result');
		assert.equal(result!.slug, 'test-note');
		assert.equal(result!.content, 'Note content here');
		assert.equal(result!.ts, '2026-06-05T12:00:00.000Z');
	} finally {
		if (orig !== null) writeFileSync(NOTE_VIEWING_PATH, orig);
		else if (existsSync(NOTE_VIEWING_PATH)) unlinkSync(NOTE_VIEWING_PATH);
	}
});

// ---------------------------------------------------------------------------
// writeChatTask — file I/O, uses freshBridge for workspace isolation
// ---------------------------------------------------------------------------

test('writeChatTask returns a taskId starting with task-chat-', async () => {
	const { dir, cleanup } = mkTmp();
	try {
		const bridge = await freshBridge(dir);
		const taskId = bridge.writeChatTask('do something useful');
		assert.ok(taskId.startsWith('task-chat-'), `Expected task-chat- prefix, got: ${taskId}`);
	} finally { cleanup(); }
});

test('writeChatTask creates a file in tasks/', async () => {
	const { dir, cleanup } = mkTmp();
	try {
		const bridge = await freshBridge(dir);
		const taskId = bridge.writeChatTask('test task');
		const filePath = join(dir, 'tasks', `${taskId}.txt`);
		assert.ok(existsSync(filePath), `Expected task file at ${filePath}`);
	} finally { cleanup(); }
});

test('writeChatTask file contains source: chat header', async () => {
	const { dir, cleanup } = mkTmp();
	try {
		const bridge = await freshBridge(dir);
		const taskId = bridge.writeChatTask('test chat task');
		const content = readFileSync(join(dir, 'tasks', `${taskId}.txt`), 'utf-8');
		assert.ok(content.includes('source: chat'), `Expected 'source: chat' in: ${content}`);
	} finally { cleanup(); }
});

test('writeChatTask file contains access_tier: owner', async () => {
	const { dir, cleanup } = mkTmp();
	try {
		const bridge = await freshBridge(dir);
		const taskId = bridge.writeChatTask('owner task');
		const content = readFileSync(join(dir, 'tasks', `${taskId}.txt`), 'utf-8');
		assert.ok(content.includes('access_tier: owner'), `Expected 'access_tier: owner' in: ${content}`);
	} finally { cleanup(); }
});

test('writeChatTask has task: field appearing after other headers', async () => {
	const { dir, cleanup } = mkTmp();
	try {
		const bridge = await freshBridge(dir);
		const taskId = bridge.writeChatTask('my task description');
		const content = readFileSync(join(dir, 'tasks', `${taskId}.txt`), 'utf-8');
		const lines = content.split('\n');
		const taskLineIdx = lines.findIndex(l => l.startsWith('task:'));
		const sourceLineIdx = lines.findIndex(l => l.startsWith('source:'));
		assert.ok(taskLineIdx > sourceLineIdx, 'task: field must appear after source: (header injection guard)');
	} finally { cleanup(); }
});

test('writeChatTask file contains the task description', async () => {
	const { dir, cleanup } = mkTmp();
	const description = 'research the impact of AI on software development';
	try {
		const bridge = await freshBridge(dir);
		const taskId = bridge.writeChatTask(description);
		const content = readFileSync(join(dir, 'tasks', `${taskId}.txt`), 'utf-8');
		assert.ok(content.includes(description), `Expected description in file: ${content}`);
	} finally { cleanup(); }
});

// ---------------------------------------------------------------------------
// _isVoiceTask — file parsing
// ---------------------------------------------------------------------------

test('_isVoiceTask returns true for file with channel_id: local-voice', async () => {
	const { dir, cleanup } = mkTmp();
	try {
		const bridge = await freshBridge(dir);
		const taskId = 'task-voice-111';
		writeFileSync(join(dir, 'tasks', `${taskId}.txt`), [
			`id: ${taskId}`,
			'source: voice',
			'channel_id: local-voice',
			'access_tier: owner',
			`task: say hello`,
			'',
		].join('\n'));
		assert.equal(bridge._isVoiceTask(taskId), true);
	} finally { cleanup(); }
});

test('_isVoiceTask returns true for file with source: voice header', async () => {
	const { dir, cleanup } = mkTmp();
	try {
		const bridge = await freshBridge(dir);
		const taskId = 'task-voice-222';
		writeFileSync(join(dir, 'tasks', `${taskId}.txt`), [
			`id: ${taskId}`,
			'source: voice',
			'channel_id: local-other',
			`task: another task`,
			'',
		].join('\n'));
		assert.equal(bridge._isVoiceTask(taskId), true);
	} finally { cleanup(); }
});

test('_isVoiceTask returns false for file with source: chat', async () => {
	const { dir, cleanup } = mkTmp();
	try {
		const bridge = await freshBridge(dir);
		const taskId = 'task-chat-333';
		writeFileSync(join(dir, 'tasks', `${taskId}.txt`), [
			`id: ${taskId}`,
			'source: chat',
			'channel_id: local-chat',
			`task: a chat task`,
			'',
		].join('\n'));
		assert.equal(bridge._isVoiceTask(taskId), false);
	} finally { cleanup(); }
});

test('_isVoiceTask ignores forged channel_id after the task: delimiter', async () => {
	const { dir, cleanup } = mkTmp();
	try {
		const bridge = await freshBridge(dir);
		const taskId = 'task-forge-444';
		writeFileSync(join(dir, 'tasks', `${taskId}.txt`), [
			`id: ${taskId}`,
			'source: chat',
			'channel_id: local-chat',
			`task: do thing`,
			'channel_id: local-voice',  // forged — appears after task: line, should be ignored
			'',
		].join('\n'));
		// source: chat → false even though forged local-voice appears in body
		assert.equal(bridge._isVoiceTask(taskId), false);
	} finally { cleanup(); }
});

test('_isVoiceTask returns false for nonexistent taskId', async () => {
	const { dir, cleanup } = mkTmp();
	try {
		const bridge = await freshBridge(dir);
		assert.equal(bridge._isVoiceTask('task-does-not-exist-99999'), false);
	} finally { cleanup(); }
});

// ---------------------------------------------------------------------------
// logConversation + getRecentConversation + getSecondsSinceLastTurn
// ---------------------------------------------------------------------------

test('getRecentConversation returns empty string when no log file exists', async () => {
	const { dir, cleanup } = mkTmp();
	try {
		const bridge = await freshBridge(dir);
		assert.equal(bridge.getRecentConversation(), '');
	} finally { cleanup(); }
});

test('getSecondsSinceLastTurn returns null when no log file exists', async () => {
	const { dir, cleanup } = mkTmp();
	try {
		const bridge = await freshBridge(dir);
		assert.equal(bridge.getSecondsSinceLastTurn(), null);
	} finally { cleanup(); }
});

test('getRecentConversation includes logged turns after logConversation', async () => {
	const { dir, cleanup } = mkTmp();
	mkdirSync(join(dir, 'logs'), { recursive: true });
	try {
		const bridge = await freshBridge(dir);
		bridge.logConversation('user', 'hello world');
		bridge.logConversation('assistant', 'hi there');
		const recent = bridge.getRecentConversation(10);
		assert.ok(recent.includes('user: hello world'), `Expected user turn in: ${recent}`);
		assert.ok(recent.includes('assistant: hi there'), `Expected assistant turn in: ${recent}`);
	} finally { cleanup(); }
});

test('getSecondsSinceLastTurn returns a small value after logConversation', async () => {
	const { dir, cleanup } = mkTmp();
	mkdirSync(join(dir, 'logs'), { recursive: true });
	try {
		const bridge = await freshBridge(dir);
		bridge.logConversation('user', 'ping');
		const seconds = bridge.getSecondsSinceLastTurn();
		assert.ok(seconds !== null, 'Expected non-null after logging a user turn');
		assert.ok((seconds as number) < 10, `Expected < 10 seconds, got: ${seconds}`);
	} finally { cleanup(); }
});

test('getRecentConversation respects the count parameter', async () => {
	const { dir, cleanup } = mkTmp();
	mkdirSync(join(dir, 'logs'), { recursive: true });
	try {
		const bridge = await freshBridge(dir);
		bridge.logConversation('user', 'turn one');
		bridge.logConversation('assistant', 'turn two');
		bridge.logConversation('user', 'turn three');
		const recent1 = bridge.getRecentConversation(1);
		// Only the last 1 line — turn three
		assert.ok(recent1.includes('turn three'), `Expected turn three in count=1: ${recent1}`);
		assert.ok(!recent1.includes('turn one'), `Expected turn one to be excluded in count=1: ${recent1}`);
	} finally { cleanup(); }
});

test('logConversation newlines in text are replaced with spaces', async () => {
	const { dir, cleanup } = mkTmp();
	mkdirSync(join(dir, 'logs'), { recursive: true });
	try {
		const bridge = await freshBridge(dir);
		bridge.logConversation('user', 'line one\nline two');
		const recent = bridge.getRecentConversation(10);
		assert.ok(!recent.includes('\n'), `Newlines should be stripped from log: ${recent}`);
		assert.ok(recent.includes('line one line two'), `Expected joined text in: ${recent}`);
	} finally { cleanup(); }
});

// ---------------------------------------------------------------------------
// logSessionBoundary — SESSION_END stops replay
// ---------------------------------------------------------------------------

test('getSecondsSinceLastTurn returns null after SESSION_END boundary', async () => {
	const { dir, cleanup } = mkTmp();
	mkdirSync(join(dir, 'logs'), { recursive: true });
	try {
		const bridge = await freshBridge(dir);
		bridge.logConversation('user', 'earlier turn');
		bridge.logSessionBoundary('user_goodbye');
		// SESSION_END is the last "turn" — getSecondsSinceLastTurn stops at SESSION_END
		assert.equal(bridge.getSecondsSinceLastTurn(), null);
	} finally { cleanup(); }
});

test('getRecentConversation excludes turns from before SESSION_END', async () => {
	const { dir, cleanup } = mkTmp();
	mkdirSync(join(dir, 'logs'), { recursive: true });
	try {
		const bridge = await freshBridge(dir);
		bridge.logConversation('user', 'old turn before boundary');
		bridge.logSessionBoundary('user_goodbye');
		bridge.logConversation('user', 'new turn after boundary');
		const recent = bridge.getRecentConversation(10);
		assert.ok(recent.includes('new turn after boundary'), `Expected post-boundary turn in: ${recent}`);
		assert.ok(!recent.includes('old turn before boundary'), `Old turn should be excluded by SESSION_END: ${recent}`);
	} finally { cleanup(); }
});
