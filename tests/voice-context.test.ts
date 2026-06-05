/**
 * Unit tests for src/voice-context.ts — buildVoiceAgentContext and
 * buildSutandoSystemPrompt.
 *
 * MEMORY_DIR, WORKSPACE_DIR, and REPO_DIR are module-scope constants
 * resolved at load time, so we use cache-busting reimports (one fresh module
 * per test group) to control the env they see.
 */

import assert from 'node:assert/strict';
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { test } from 'node:test';
import { pathToFileURL } from 'node:url';
import { fileURLToPath } from 'node:url';

const SRC = fileURLToPath(new URL('../src/voice-context.ts', import.meta.url));
const srcUrl = pathToFileURL(SRC).href;

async function freshImport(memDir: string, workspace: string): Promise<typeof import('../src/voice-context.ts')> {
	const origMem = process.env.SUTANDO_MEMORY_DIR;
	const origWs = process.env.SUTANDO_WORKSPACE;
	process.env.SUTANDO_MEMORY_DIR = memDir;
	process.env.SUTANDO_WORKSPACE = workspace;
	try {
		return await import(`${srcUrl}?t=${Date.now()}`);
	} finally {
		if (origMem === undefined) delete process.env.SUTANDO_MEMORY_DIR;
		else process.env.SUTANDO_MEMORY_DIR = origMem;
		if (origWs === undefined) delete process.env.SUTANDO_WORKSPACE;
		else process.env.SUTANDO_WORKSPACE = origWs;
	}
}

function mkTmp(): { dir: string; mem: string; ws: string; cleanup: () => void } {
	const dir = join('/tmp', `vc-test-${Date.now()}-${Math.floor(Math.random() * 1e6)}`);
	const mem = join(dir, 'memory');
	const ws = join(dir, 'workspace');
	mkdirSync(mem, { recursive: true });
	mkdirSync(join(ws, 'state'), { recursive: true });
	return { dir, mem, ws, cleanup: () => rmSync(dir, { recursive: true, force: true }) };
}

// ---------------------------------------------------------------------------
// buildSutandoSystemPrompt
// ---------------------------------------------------------------------------

test('buildSutandoSystemPrompt includes base identity text', async () => {
	const { dir, mem, ws, cleanup } = mkTmp();
	try {
		const mod = await freshImport(mem, ws);
		const result = mod.buildSutandoSystemPrompt();
		assert.ok(result.includes("You are Sutando"), `Missing identity line, got: ${result.slice(0, 200)}`);
	} finally { cleanup(); }
});

test('buildSutandoSystemPrompt includes ## Memory section', async () => {
	const { dir, mem, ws, cleanup } = mkTmp();
	try {
		const mod = await freshImport(mem, ws);
		const result = mod.buildSutandoSystemPrompt();
		assert.ok(result.includes('## Memory'), 'Missing ## Memory section');
	} finally { cleanup(); }
});

test('buildSutandoSystemPrompt includes user context when user_profile.md exists', async () => {
	const { dir, mem, ws, cleanup } = mkTmp();
	try {
		writeFileSync(join(mem, 'user_profile.md'), 'Bassil is a software engineer.');
		const mod = await freshImport(mem, ws);
		const result = mod.buildSutandoSystemPrompt();
		assert.ok(result.includes('## User context'), 'Missing ## User context section');
		assert.ok(result.includes('Bassil is a software engineer'), 'Missing profile content');
	} finally { cleanup(); }
});

test('buildSutandoSystemPrompt omits user context when user_profile.md missing', async () => {
	const { dir, mem, ws, cleanup } = mkTmp();
	try {
		const mod = await freshImport(mem, ws);
		const result = mod.buildSutandoSystemPrompt();
		assert.ok(!result.includes('## User context'), 'Should omit ## User context when no profile');
	} finally { cleanup(); }
});

test('buildSutandoSystemPrompt strips YAML frontmatter from memory files', async () => {
	const { dir, mem, ws, cleanup } = mkTmp();
	try {
		writeFileSync(join(mem, 'user_profile.md'), [
			'---',
			'name: user-profile',
			'type: user',
			'---',
			'',
			'Bassil is the founder.',
		].join('\n'));
		const mod = await freshImport(mem, ws);
		const result = mod.buildSutandoSystemPrompt();
		assert.ok(!result.includes('name: user-profile'), 'Frontmatter should be stripped');
		assert.ok(result.includes('Bassil is the founder'), 'Body content should be preserved');
	} finally { cleanup(); }
});

test('buildSutandoSystemPrompt includes response style when file exists', async () => {
	const { dir, mem, ws, cleanup } = mkTmp();
	try {
		writeFileSync(join(mem, 'feedback_response_style.md'), 'Be concise.');
		const mod = await freshImport(mem, ws);
		const result = mod.buildSutandoSystemPrompt();
		assert.ok(result.includes('## Communication style'), 'Missing ## Communication style');
		assert.ok(result.includes('Be concise'), 'Missing style content');
	} finally { cleanup(); }
});

// ---------------------------------------------------------------------------
// buildVoiceAgentContext
// ---------------------------------------------------------------------------

test('buildVoiceAgentContext returns empty string when no files exist', async () => {
	const { dir, mem, ws, cleanup } = mkTmp();
	try {
		const mod = await freshImport(mem, ws);
		const result = mod.buildVoiceAgentContext();
		assert.equal(result.trim(), '', `Expected empty result, got: ${result.slice(0, 200)}`);
	} finally { cleanup(); }
});

test('buildVoiceAgentContext includes USER CONTEXT when user_profile.md exists', async () => {
	const { dir, mem, ws, cleanup } = mkTmp();
	try {
		writeFileSync(join(mem, 'user_profile.md'), 'Bassil is a founder.');
		const mod = await freshImport(mem, ws);
		const result = mod.buildVoiceAgentContext();
		assert.ok(result.includes('USER CONTEXT:'), 'Missing USER CONTEXT section');
		assert.ok(result.includes('Bassil is a founder'), 'Missing profile content');
	} finally { cleanup(); }
});

test('buildVoiceAgentContext omits USER CONTEXT when user_profile.md missing', async () => {
	const { dir, mem, ws, cleanup } = mkTmp();
	try {
		const mod = await freshImport(mem, ws);
		const result = mod.buildVoiceAgentContext();
		assert.ok(!result.includes('USER CONTEXT:'), 'Should omit USER CONTEXT without profile');
	} finally { cleanup(); }
});

test('buildVoiceAgentContext includes SYSTEM STATUS when build_log has Score', async () => {
	const { dir, mem, ws, cleanup } = mkTmp();
	try {
		writeFileSync(join(ws, 'build_log.md'), '**Score: 9/10 — all green**\n');
		const mod = await freshImport(mem, ws);
		const result = mod.buildVoiceAgentContext();
		assert.ok(result.includes('SYSTEM STATUS:'), 'Missing SYSTEM STATUS');
		assert.ok(result.includes('9/10'), 'Missing score value');
	} finally { cleanup(); }
});

test('buildVoiceAgentContext includes RECENT ACTIVITY when build_log has dated section', async () => {
	const { dir, mem, ws, cleanup } = mkTmp();
	try {
		writeFileSync(join(ws, 'build_log.md'), [
			'## 2026-06-05 — Pass 855',
			'- **voice-config.test.ts**: 16 tests added',
		].join('\n') + '\n');
		const mod = await freshImport(mem, ws);
		const result = mod.buildVoiceAgentContext();
		assert.ok(result.includes('RECENT ACTIVITY:'), 'Missing RECENT ACTIVITY');
		assert.ok(result.includes('2026-06-05'), 'Missing date');
	} finally { cleanup(); }
});

test('buildVoiceAgentContext truncates user profile to 500 chars', async () => {
	const { dir, mem, ws, cleanup } = mkTmp();
	try {
		writeFileSync(join(mem, 'user_profile.md'), 'X'.repeat(1000));
		const mod = await freshImport(mem, ws);
		const result = mod.buildVoiceAgentContext();
		// The profile body is sliced to 500; the output should not contain 1000 Xs
		const xRun = result.match(/X+/)?.[0] ?? '';
		assert.ok(xRun.length <= 500, `Profile not truncated to 500, got ${xRun.length} chars`);
	} finally { cleanup(); }
});
