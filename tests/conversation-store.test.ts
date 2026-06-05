/**
 * Unit tests for src/conversation-store.ts.
 *
 * sourceFromRole / kindFromRole are pure functions — tested directly.
 *
 * DB-writing functions (recordConversation, recordToolCall, recordSession,
 * recordSessionBoundary) require SUTANDO_CONVERSATION_DB pointing at a temp
 * file BEFORE the module loads (DB_PATH is a module-scope constant). Each DB
 * test uses a fresh dynamic import with a unique `?t=` cache-buster to get an
 * isolated module instance with its own db + initFailed state.
 */

import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { mkdirSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { test } from 'node:test';

import { sourceFromRole, kindFromRole } from '../src/conversation-store.ts';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mkTmp(): { dir: string; cleanup: () => void } {
	const dir = join('/tmp', `cs-test-${Date.now()}-${Math.floor(Math.random() * 1e6)}`);
	mkdirSync(dir, { recursive: true });
	return { dir, cleanup: () => rmSync(dir, { recursive: true, force: true }) };
}

type StoreModule = typeof import('../src/conversation-store.ts');

/** Fresh module import with SUTANDO_CONVERSATION_DB set to a temp path. */
async function freshStore(dbPath: string): Promise<StoreModule> {
	const origDb = process.env.SUTANDO_CONVERSATION_DB;
	process.env.SUTANDO_CONVERSATION_DB = dbPath;
	try {
		const srcUrl = pathToFileURL(
			join(process.cwd(), 'src', 'conversation-store.ts'),
		).href;
		return (await import(`${srcUrl}?t=${Date.now()}`)) as StoreModule;
	} finally {
		if (origDb === undefined) delete process.env.SUTANDO_CONVERSATION_DB;
		else process.env.SUTANDO_CONVERSATION_DB = origDb;
	}
}

// ---------------------------------------------------------------------------
// sourceFromRole — pure function
// ---------------------------------------------------------------------------

test('sourceFromRole: phone- prefix → "phone"', () => {
	assert.equal(sourceFromRole('phone-caller'), 'phone');
	assert.equal(sourceFromRole('phone-agent'), 'phone');
	assert.equal(sourceFromRole('phone-user'), 'phone');
});

test('sourceFromRole: discord- prefix → "discord-voice"', () => {
	assert.equal(sourceFromRole('discord-user'), 'discord-voice');
	assert.equal(sourceFromRole('discord-agent'), 'discord-voice');
	assert.equal(sourceFromRole('discord-peer'), 'discord-voice');
});

test('sourceFromRole: everything else → "voice"', () => {
	assert.equal(sourceFromRole('user'), 'voice');
	assert.equal(sourceFromRole('assistant'), 'voice');
	assert.equal(sourceFromRole('sutando'), 'voice');
	assert.equal(sourceFromRole('SESSION_END'), 'voice');
});

// ---------------------------------------------------------------------------
// kindFromRole — pure function
// ---------------------------------------------------------------------------

test('kindFromRole: "user" → "user"', () => {
	assert.equal(kindFromRole('user'), 'user');
});

test('kindFromRole: *-user suffix → "user"', () => {
	assert.equal(kindFromRole('phone-user'), 'user');
	assert.equal(kindFromRole('discord-user'), 'user');
});

test('kindFromRole: *-caller suffix → "user"', () => {
	assert.equal(kindFromRole('phone-caller'), 'user');
});

test('kindFromRole: "assistant" and "sutando" → "agent"', () => {
	assert.equal(kindFromRole('assistant'), 'agent');
	assert.equal(kindFromRole('sutando'), 'agent');
});

test('kindFromRole: *-agent suffix → "agent"', () => {
	assert.equal(kindFromRole('phone-agent'), 'agent');
	assert.equal(kindFromRole('discord-agent'), 'agent');
	assert.equal(kindFromRole('voice-agent'), 'agent');
});

test('kindFromRole: *-assistant suffix → "agent"', () => {
	assert.equal(kindFromRole('discord-assistant'), 'agent');
});

test('kindFromRole: "discord-peer" → "peer"', () => {
	assert.equal(kindFromRole('discord-peer'), 'peer');
});

test('kindFromRole: unknown roles pass through verbatim', () => {
	assert.equal(kindFromRole('SESSION_END'), 'SESSION_END');
	assert.equal(kindFromRole('system'), 'system');
	assert.equal(kindFromRole('error'), 'error');
});

// ---------------------------------------------------------------------------
// recordConversation — DB round-trip
// ---------------------------------------------------------------------------

test('recordConversation inserts a row into the voice table', async () => {
	const { dir, cleanup } = mkTmp();
	const dbPath = join(dir, 'conv.sqlite');
	try {
		const store = await freshStore(dbPath);
		store.recordConversation('user', 'hello world', 'sess-1');

		const db = new DatabaseSync(dbPath);
		const rows = db.prepare('SELECT kind, text, session_id FROM voice ORDER BY id').all() as { kind: string; text: string; session_id: string | null }[];
		db.close();

		assert.equal(rows.length, 1);
		assert.equal(rows[0].kind, 'user');
		assert.equal(rows[0].text, 'hello world');
		assert.equal(rows[0].session_id, 'sess-1');
	} finally { cleanup(); }
});

test('recordConversation routes phone- role to phone table', async () => {
	const { dir, cleanup } = mkTmp();
	const dbPath = join(dir, 'conv.sqlite');
	try {
		const store = await freshStore(dbPath);
		store.recordConversation('phone-caller', 'hi from phone', 'sess-p');

		const db = new DatabaseSync(dbPath);
		const rows = db.prepare('SELECT kind, text FROM phone ORDER BY id').all() as { kind: string; text: string }[];
		// voice table should be empty
		const voiceRows = db.prepare('SELECT COUNT(*) as c FROM voice').get() as { c: number };
		db.close();

		assert.equal(rows.length, 1);
		assert.equal(rows[0].kind, 'user');
		assert.equal(rows[0].text, 'hi from phone');
		assert.equal(voiceRows.c, 0);
	} finally { cleanup(); }
});

test('recordConversation routes discord- role to discord_voice table', async () => {
	const { dir, cleanup } = mkTmp();
	const dbPath = join(dir, 'conv.sqlite');
	try {
		const store = await freshStore(dbPath);
		store.recordConversation('discord-user', 'hey discord', 'sess-d');

		const db = new DatabaseSync(dbPath);
		const rows = db.prepare('SELECT kind, text FROM discord_voice ORDER BY id').all() as { kind: string; text: string }[];
		db.close();

		assert.equal(rows.length, 1);
		assert.equal(rows[0].kind, 'user');
		assert.equal(rows[0].text, 'hey discord');
	} finally { cleanup(); }
});

// ---------------------------------------------------------------------------
// recordSessionBoundary — delegates to recordConversation
// ---------------------------------------------------------------------------

test('recordSessionBoundary inserts SESSION_END kind into voice table', async () => {
	const { dir, cleanup } = mkTmp();
	const dbPath = join(dir, 'conv.sqlite');
	try {
		const store = await freshStore(dbPath);
		store.recordSessionBoundary('user_goodbye', 'sess-end');

		const db = new DatabaseSync(dbPath);
		const rows = db.prepare('SELECT kind, text FROM voice ORDER BY id').all() as { kind: string; text: string }[];
		db.close();

		assert.equal(rows.length, 1);
		assert.equal(rows[0].kind, 'SESSION_END');
		assert.equal(rows[0].text, 'user_goodbye');
	} finally { cleanup(); }
});

// ---------------------------------------------------------------------------
// recordToolCall
// ---------------------------------------------------------------------------

test('recordToolCall inserts tool_call row into correct surface table', async () => {
	const { dir, cleanup } = mkTmp();
	const dbPath = join(dir, 'conv.sqlite');
	try {
		const store = await freshStore(dbPath);
		store.recordToolCall('voice', 'get_weather', 250, 'sess-tc');

		const db = new DatabaseSync(dbPath);
		const rows = db.prepare('SELECT kind, text, duration_ms FROM voice ORDER BY id').all() as { kind: string; text: string; duration_ms: number | null }[];
		db.close();

		assert.equal(rows.length, 1);
		assert.equal(rows[0].kind, 'tool_call');
		assert.equal(rows[0].text, 'get_weather');
		assert.equal(rows[0].duration_ms, 250);
	} finally { cleanup(); }
});

// ---------------------------------------------------------------------------
// recordSession
// ---------------------------------------------------------------------------

test('recordSession inserts a sessions row', async () => {
	const { dir, cleanup } = mkTmp();
	const dbPath = join(dir, 'conv.sqlite');
	try {
		const store = await freshStore(dbPath);
		store.recordSession({
			source: 'voice',
			sessionId: 'sess-r',
			durationMs: 12000,
			transcriptLines: 5,
			toolCount: 2,
		});

		const db = new DatabaseSync(dbPath);
		const row = db.prepare('SELECT source, session_id, duration_ms FROM sessions ORDER BY ts_unix DESC LIMIT 1').get() as { source: string; session_id: string; duration_ms: number } | undefined;
		db.close();

		assert.ok(row, 'Expected a sessions row');
		assert.equal(row.source, 'voice');
		assert.equal(row.session_id, 'sess-r');
		assert.equal(row.duration_ms, 12000);
	} finally { cleanup(); }
});
