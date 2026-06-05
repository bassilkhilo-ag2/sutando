/**
 * Unit tests for src/workspace_default.ts — resolveWorkspace, statusPath,
 * statusReadPath.
 *
 * All tests override SUTANDO_WORKSPACE via process.env and restore it in
 * teardown. The module caches `_fallbackWarnPrinted` at module scope —
 * we reimport with a cache-busting query param so each env-flag test gets
 * a fresh module instance.
 */

import assert from 'node:assert/strict';
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { pathToFileURL } from 'node:url';

const SRC = new URL('../src/workspace_default.ts', import.meta.url).pathname;
const srcUrl = pathToFileURL(SRC).href;

async function freshImport(): Promise<typeof import('../src/workspace_default.ts')> {
	return import(`${srcUrl}?t=${Date.now()}`);
}

// ---------------------------------------------------------------------------
// resolveWorkspace
// ---------------------------------------------------------------------------

test('resolveWorkspace returns SUTANDO_WORKSPACE env var when set', async () => {
	const orig = process.env.SUTANDO_WORKSPACE;
	process.env.SUTANDO_WORKSPACE = '/tmp/test-workspace-abc';
	try {
		const mod = await freshImport();
		assert.equal(mod.resolveWorkspace(), '/tmp/test-workspace-abc');
	} finally {
		if (orig === undefined) delete process.env.SUTANDO_WORKSPACE;
		else process.env.SUTANDO_WORKSPACE = orig;
	}
});

test('resolveWorkspace expands leading ~ in env var', async () => {
	const orig = process.env.SUTANDO_WORKSPACE;
	process.env.SUTANDO_WORKSPACE = '~/.sutando/workspace';
	try {
		const mod = await freshImport();
		const result = mod.resolveWorkspace();
		assert.ok(!result.startsWith('~'), `Expected tilde expanded, got: ${result}`);
		assert.ok(result.startsWith(homedir()), `Expected to start with ${homedir()}, got: ${result}`);
	} finally {
		if (orig === undefined) delete process.env.SUTANDO_WORKSPACE;
		else process.env.SUTANDO_WORKSPACE = orig;
	}
});

test('resolveWorkspace falls back to ~/.sutando/workspace when env unset', async () => {
	const orig = process.env.SUTANDO_WORKSPACE;
	delete process.env.SUTANDO_WORKSPACE;
	try {
		const mod = await freshImport();
		const expected = join(homedir(), '.sutando', 'workspace');
		assert.equal(mod.resolveWorkspace(), expected);
	} finally {
		if (orig !== undefined) process.env.SUTANDO_WORKSPACE = orig;
	}
});

test('resolveWorkspace trims whitespace from env var', async () => {
	const orig = process.env.SUTANDO_WORKSPACE;
	process.env.SUTANDO_WORKSPACE = '  /tmp/trimmed-ws  ';
	try {
		const mod = await freshImport();
		assert.equal(mod.resolveWorkspace(), '/tmp/trimmed-ws');
	} finally {
		if (orig === undefined) delete process.env.SUTANDO_WORKSPACE;
		else process.env.SUTANDO_WORKSPACE = orig;
	}
});

// ---------------------------------------------------------------------------
// statusPath
// ---------------------------------------------------------------------------

test('statusPath builds <workspace>/state/<name>', async () => {
	const mod = await freshImport();
	const result = mod.statusPath('core-status.json', '/tmp/ws');
	assert.equal(result, '/tmp/ws/state/core-status.json');
});

test('statusPath uses resolveWorkspace when no workspace arg provided', async () => {
	const orig = process.env.SUTANDO_WORKSPACE;
	process.env.SUTANDO_WORKSPACE = '/tmp/env-ws';
	try {
		const mod = await freshImport();
		const result = mod.statusPath('health.json');
		assert.equal(result, '/tmp/env-ws/state/health.json');
	} finally {
		if (orig === undefined) delete process.env.SUTANDO_WORKSPACE;
		else process.env.SUTANDO_WORKSPACE = orig;
	}
});

// ---------------------------------------------------------------------------
// statusReadPath
// ---------------------------------------------------------------------------

test('statusReadPath returns state/<name> when it exists', async () => {
	const mod = await freshImport();
	const tmp = join('/tmp', `sut-test-${Date.now()}`);
	mkdirSync(join(tmp, 'state'), { recursive: true });
	writeFileSync(join(tmp, 'state', 'core-status.json'), '{}');
	try {
		const result = mod.statusReadPath('core-status.json', tmp);
		assert.equal(result, join(tmp, 'state', 'core-status.json'));
	} finally {
		rmSync(tmp, { recursive: true, force: true });
	}
});

test('statusReadPath falls back to legacy root path when state/<name> missing', async () => {
	const mod = await freshImport();
	const tmp = join('/tmp', `sut-test-${Date.now()}`);
	mkdirSync(join(tmp, 'state'), { recursive: true });
	// Write to legacy root, NOT state/
	writeFileSync(join(tmp, 'core-status.json'), '{}');
	try {
		const result = mod.statusReadPath('core-status.json', tmp);
		assert.equal(result, join(tmp, 'core-status.json'));
	} finally {
		rmSync(tmp, { recursive: true, force: true });
	}
});

test('statusReadPath returns state/<name> when neither path exists', async () => {
	const mod = await freshImport();
	const tmp = '/tmp/definitely-does-not-exist-xyzzy';
	const result = mod.statusReadPath('core-status.json', tmp);
	assert.equal(result, join(tmp, 'state', 'core-status.json'));
});

test('statusReadPath prefers state/<name> over legacy root when both exist', async () => {
	const mod = await freshImport();
	const tmp = join('/tmp', `sut-test-${Date.now()}`);
	mkdirSync(join(tmp, 'state'), { recursive: true });
	writeFileSync(join(tmp, 'state', 'core-status.json'), '{"from":"state"}');
	writeFileSync(join(tmp, 'core-status.json'), '{"from":"root"}');
	try {
		const result = mod.statusReadPath('core-status.json', tmp);
		assert.equal(result, join(tmp, 'state', 'core-status.json'));
	} finally {
		rmSync(tmp, { recursive: true, force: true });
	}
});
