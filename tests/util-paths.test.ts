/**
 * Unit tests for src/util_paths.ts — sharedPersonalPath, claudeHomePath,
 * and the personalPath workspace-fallback branches.
 *
 * memoryDirEnv and the personalPath SUTANDO_HOST_LABEL variants are covered
 * in tests/util-paths-memory-dir.test.ts.
 */

import assert from 'node:assert/strict';
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';

import { claudeHomePath, personalPath, sharedPersonalPath } from '../src/util_paths.js';

function clearEnv() {
	delete process.env.SUTANDO_MEMORY_DIR;
	delete process.env.SUTANDO_PRIVATE_DIR;
	delete process.env.SUTANDO_HOST_LABEL;
	delete process.env.CLAUDE_HOME;
	delete process.env.SUTANDO_WORKSPACE;
}

function mkTmp(): { dir: string; cleanup: () => void } {
	const dir = join('/tmp', `up-test-${Date.now()}-${Math.floor(Math.random() * 1e6)}`);
	mkdirSync(dir, { recursive: true });
	return { dir, cleanup: () => rmSync(dir, { recursive: true, force: true }) };
}

// ---------------------------------------------------------------------------
// claudeHomePath
// ---------------------------------------------------------------------------

test('claudeHomePath returns ~/.claude when CLAUDE_HOME is unset', () => {
	clearEnv();
	const result = claudeHomePath();
	assert.equal(result, join(homedir(), '.claude'));
});

test('claudeHomePath joins subpath components', () => {
	clearEnv();
	const result = claudeHomePath('channels', 'discord', 'access.json');
	assert.equal(result, join(homedir(), '.claude', 'channels', 'discord', 'access.json'));
});

test('claudeHomePath uses CLAUDE_HOME override when set', () => {
	clearEnv();
	process.env.CLAUDE_HOME = '/tmp/test-claude-home';
	try {
		const result = claudeHomePath();
		assert.equal(result, '/tmp/test-claude-home');
	} finally { clearEnv(); }
});

test('claudeHomePath expands ~ in CLAUDE_HOME', () => {
	clearEnv();
	process.env.CLAUDE_HOME = '~/.test-claude';
	try {
		const result = claudeHomePath();
		assert.ok(!result.startsWith('~'), `Expected ~ expanded, got: ${result}`);
		assert.ok(result.startsWith(homedir()), `Expected homedir prefix, got: ${result}`);
	} finally { clearEnv(); }
});

test('claudeHomePath joins subpath under CLAUDE_HOME override', () => {
	clearEnv();
	process.env.CLAUDE_HOME = '/tmp/test-claude-home';
	try {
		const result = claudeHomePath('skills', 'my-skill');
		assert.equal(result, '/tmp/test-claude-home/skills/my-skill');
	} finally { clearEnv(); }
});

// ---------------------------------------------------------------------------
// sharedPersonalPath
// ---------------------------------------------------------------------------

test('sharedPersonalPath falls back to workspace path when no memory dir set', () => {
	clearEnv();
	const { dir: ws, cleanup } = mkTmp();
	try {
		const result = sharedPersonalPath('notes', ws);
		assert.equal(result, join(ws, 'notes'));
	} finally { cleanup(); clearEnv(); }
});

test('sharedPersonalPath returns memory-dir candidate when SUTANDO_MEMORY_DIR is set and file does not exist', () => {
	clearEnv();
	const { dir: mem, cleanup: cleanMem } = mkTmp();
	const { dir: ws, cleanup: cleanWs } = mkTmp();
	try {
		process.env.SUTANDO_MEMORY_DIR = mem;
		const result = sharedPersonalPath('notes', ws);
		// Neither mem/notes nor ws/notes exists → returns mem/notes (preferred)
		assert.equal(result, join(mem, 'notes'));
	} finally { cleanMem(); cleanWs(); clearEnv(); }
});

test('sharedPersonalPath returns memory-dir file when it exists', () => {
	clearEnv();
	const { dir: mem, cleanup: cleanMem } = mkTmp();
	const { dir: ws, cleanup: cleanWs } = mkTmp();
	try {
		process.env.SUTANDO_MEMORY_DIR = mem;
		writeFileSync(join(mem, 'notes'), 'fleet notes');
		const result = sharedPersonalPath('notes', ws);
		assert.equal(result, join(mem, 'notes'));
	} finally { cleanMem(); cleanWs(); clearEnv(); }
});

test('sharedPersonalPath falls back to workspace when memory file missing but ws file exists', () => {
	clearEnv();
	const { dir: mem, cleanup: cleanMem } = mkTmp();
	const { dir: ws, cleanup: cleanWs } = mkTmp();
	try {
		process.env.SUTANDO_MEMORY_DIR = mem;
		// Only ws copy exists — mem/notes does NOT exist
		writeFileSync(join(ws, 'notes'), 'ws notes');
		const result = sharedPersonalPath('notes', ws);
		assert.equal(result, join(ws, 'notes'));
	} finally { cleanMem(); cleanWs(); clearEnv(); }
});

// ---------------------------------------------------------------------------
// personalPath — workspace fallback branch
// ---------------------------------------------------------------------------

test('personalPath falls back to ws path when no memory dir and file does not exist', () => {
	clearEnv();
	const { dir: ws, cleanup } = mkTmp();
	try {
		const result = personalPath('pending-questions.md', ws);
		assert.equal(result, join(ws, 'pending-questions.md'));
	} finally { cleanup(); clearEnv(); }
});

test('personalPath returns workspace file when it exists and no memory dir', () => {
	clearEnv();
	const { dir: ws, cleanup } = mkTmp();
	try {
		writeFileSync(join(ws, 'pending-questions.md'), '## Pending');
		const result = personalPath('pending-questions.md', ws);
		assert.equal(result, join(ws, 'pending-questions.md'));
	} finally { cleanup(); clearEnv(); }
});

test('personalPath returns assets path for stand-avatar.png when no memory dir', () => {
	clearEnv();
	const { dir: ws, cleanup } = mkTmp();
	try {
		// No memory dir, no assets/ dir — should fall back to assets path
		const result = personalPath('stand-avatar.png', ws);
		assert.equal(result, join(ws, 'assets', 'stand-avatar.png'));
	} finally { cleanup(); clearEnv(); }
});

test('personalPath returns assets/stand-avatar.png when assets file exists and no memory dir', () => {
	clearEnv();
	const { dir: ws, cleanup } = mkTmp();
	try {
		mkdirSync(join(ws, 'assets'), { recursive: true });
		writeFileSync(join(ws, 'assets', 'stand-avatar.png'), 'PNG');
		const result = personalPath('stand-avatar.png', ws);
		assert.equal(result, join(ws, 'assets', 'stand-avatar.png'));
	} finally { cleanup(); clearEnv(); }
});
