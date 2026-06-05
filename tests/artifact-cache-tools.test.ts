/**
 * Unit tests for src/artifact-cache-tools.ts —
 * setActiveArtifactTool, queryActiveArtifactTool, clearActiveArtifactTool,
 * and the clearActiveArtifact() helper.
 *
 * activeArtifact is module-level state; tests call clearActiveArtifactTool
 * (or clearActiveArtifact()) in teardown to isolate state across tests.
 */

import assert from 'node:assert/strict';
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { test } from 'node:test';

import {
	clearActiveArtifact,
	setActiveArtifactTool,
	queryActiveArtifactTool,
	clearActiveArtifactTool,
} from '../src/artifact-cache-tools.ts';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type AnyRecord = Record<string, unknown>;

async function setArtifact(path: string): Promise<AnyRecord> {
	return (setActiveArtifactTool.execute as (a: AnyRecord) => Promise<AnyRecord>)({ path });
}

async function queryArtifact(query: string): Promise<AnyRecord> {
	return (queryActiveArtifactTool.execute as (a: AnyRecord) => Promise<AnyRecord>)({ query });
}

async function clearArtifact(): Promise<AnyRecord> {
	return (clearActiveArtifactTool.execute as (a: AnyRecord) => Promise<AnyRecord>)({});
}

function mkTmp(): { dir: string; cleanup: () => void } {
	const d = join('/tmp', `act-test-${Date.now()}-${Math.floor(Math.random() * 1e6)}`);
	mkdirSync(d, { recursive: true });
	return { dir: d, cleanup: () => rmSync(d, { recursive: true, force: true }) };
}

// ---------------------------------------------------------------------------
// Tool metadata
// ---------------------------------------------------------------------------

test('setActiveArtifactTool has correct name and execution', () => {
	assert.equal(setActiveArtifactTool.name, 'set_active_artifact');
	assert.equal(setActiveArtifactTool.execution, 'inline');
});

test('queryActiveArtifactTool has correct name and execution', () => {
	assert.equal(queryActiveArtifactTool.name, 'query_active_artifact');
	assert.equal(queryActiveArtifactTool.execution, 'inline');
});

test('clearActiveArtifactTool has correct name and execution', () => {
	assert.equal(clearActiveArtifactTool.name, 'clear_active_artifact');
	assert.equal(clearActiveArtifactTool.execution, 'inline');
});

// ---------------------------------------------------------------------------
// clearActiveArtifactTool
// ---------------------------------------------------------------------------

test('clearActiveArtifactTool when nothing loaded returns ok and cleared:null', async () => {
	clearActiveArtifact(); // ensure clean state
	const result = await clearArtifact();
	assert.equal(result.ok, true);
	assert.equal(result.cleared, null);
});

test('clearActiveArtifactTool after loading returns the cleared path', async () => {
	const { dir, cleanup } = mkTmp();
	try {
		const p = join(dir, 'doc.txt');
		writeFileSync(p, 'hello world');
		await setArtifact(p);
		const result = await clearArtifact();
		assert.equal(result.ok, true);
		assert.equal(result.cleared, p);
	} finally { cleanup(); clearActiveArtifact(); }
});

test('clearActiveArtifact() helper clears state (second clearActiveArtifactTool returns null)', async () => {
	const { dir, cleanup } = mkTmp();
	try {
		const p = join(dir, 'doc.txt');
		writeFileSync(p, 'hello');
		await setArtifact(p);
		clearActiveArtifact(); // direct helper
		const result = await clearArtifact();
		assert.equal(result.cleared, null); // already gone
	} finally { cleanup(); }
});

// ---------------------------------------------------------------------------
// setActiveArtifactTool
// ---------------------------------------------------------------------------

test('setActiveArtifactTool returns error for missing file', async () => {
	clearActiveArtifact();
	const result = await setArtifact('/tmp/definitely-no-such-file-act-test.txt');
	assert.ok('error' in result, `Expected error, got: ${JSON.stringify(result)}`);
});

test('setActiveArtifactTool loads a plain text file', async () => {
	const { dir, cleanup } = mkTmp();
	try {
		const p = join(dir, 'notes.txt');
		writeFileSync(p, 'Line 1\nLine 2\nLine 3\n');
		const result = await setArtifact(p);
		assert.equal(result.artifact_id, p);
		assert.equal(result.n_chars, 21);
		assert.ok(typeof result.summary === 'string');
	} finally { cleanup(); clearActiveArtifact(); }
});

test('setActiveArtifactTool detects sections in markdown', async () => {
	const { dir, cleanup } = mkTmp();
	try {
		const p = join(dir, 'doc.md');
		writeFileSync(p, '# Introduction\nhello\n## Methods\nstuff\n### Results\ndata\n');
		const result = await setArtifact(p);
		assert.ok((result.n_sections as number) >= 3, `Expected >= 3 sections, got ${result.n_sections}`);
	} finally { cleanup(); clearActiveArtifact(); }
});

test('setActiveArtifactTool detects sections in TypeScript', async () => {
	const { dir, cleanup } = mkTmp();
	try {
		const p = join(dir, 'code.ts');
		writeFileSync(p, 'export function foo() {}\nexport class Bar {}\nexport async function baz() {}\n');
		const result = await setArtifact(p);
		assert.ok((result.n_sections as number) >= 2, `Expected >= 2 sections, got ${result.n_sections}`);
	} finally { cleanup(); clearActiveArtifact(); }
});

test('setActiveArtifactTool returns 0 sections for unknown extension', async () => {
	const { dir, cleanup } = mkTmp();
	try {
		const p = join(dir, 'data.csv');
		writeFileSync(p, 'a,b,c\n1,2,3\n');
		const result = await setArtifact(p);
		assert.equal(result.n_sections, 0);
	} finally { cleanup(); clearActiveArtifact(); }
});

test('setActiveArtifactTool summary includes char and line counts', async () => {
	const { dir, cleanup } = mkTmp();
	try {
		const p = join(dir, 'doc.txt');
		writeFileSync(p, 'abc\ndef\n');
		const result = await setArtifact(p);
		const summary = result.summary as string;
		assert.ok(summary.includes('chars'), `Summary should mention chars: ${summary}`);
		assert.ok(summary.includes('lines'), `Summary should mention lines: ${summary}`);
	} finally { cleanup(); clearActiveArtifact(); }
});

test('setActiveArtifactTool expands ~ in path', async () => {
	const { dir, cleanup } = mkTmp();
	try {
		// Write a file in home dir and load it via ~ path
		const homeSub = join(process.env.HOME || '/tmp', '.sutando-test-artifact.txt');
		writeFileSync(homeSub, 'tilde test');
		try {
			const result = await setArtifact('~/.sutando-test-artifact.txt');
			assert.equal(result.artifact_id, homeSub);
		} finally {
			rmSync(homeSub, { force: true });
		}
	} finally { cleanup(); clearActiveArtifact(); }
});

// ---------------------------------------------------------------------------
// queryActiveArtifactTool
// ---------------------------------------------------------------------------

test('queryActiveArtifactTool returns error when no artifact loaded', async () => {
	clearActiveArtifact();
	const result = await queryArtifact('anything');
	assert.ok('error' in result, `Expected error, got: ${JSON.stringify(result)}`);
	assert.ok((result.error as string).includes('No active artifact'));
});

test('queryActiveArtifactTool returns excerpt for keyword match', async () => {
	const { dir, cleanup } = mkTmp();
	try {
		const p = join(dir, 'doc.txt');
		writeFileSync(p, 'apple orange\nbanana mango\ngrape kiwi\n');
		await setArtifact(p);
		const result = await queryArtifact('banana');
		assert.ok('excerpt' in result);
		assert.ok((result.excerpt as string).includes('banana'));
	} finally { cleanup(); clearActiveArtifact(); }
});

test('queryActiveArtifactTool returns section match over keyword match in markdown', async () => {
	const { dir, cleanup } = mkTmp();
	try {
		const p = join(dir, 'doc.md');
		writeFileSync(p, '# Introduction\nsome intro text\n## Methods\nsteps here\n## Results\nfindings\n');
		await setArtifact(p);
		const result = await queryArtifact('Methods');
		assert.ok('section' in result);
		assert.ok((result.section as string).includes('Methods'));
		assert.ok((result.excerpt as string).includes('steps here'));
	} finally { cleanup(); clearActiveArtifact(); }
});

test('queryActiveArtifactTool returns no-match message for unrelated query', async () => {
	const { dir, cleanup } = mkTmp();
	try {
		const p = join(dir, 'doc.txt');
		writeFileSync(p, 'apple orange banana\n');
		await setArtifact(p);
		const result = await queryArtifact('ZZZZNOTFOUND');
		assert.ok((result.excerpt as string).includes('No matches'));
	} finally { cleanup(); clearActiveArtifact(); }
});

test('queryActiveArtifactTool includes artifact_id and line_range in result', async () => {
	const { dir, cleanup } = mkTmp();
	try {
		const p = join(dir, 'doc.txt');
		writeFileSync(p, 'alpha\nbeta\ngamma\n');
		await setArtifact(p);
		const result = await queryArtifact('beta');
		assert.equal(result.artifact_id, p);
		assert.ok(Array.isArray(result.line_range), 'Expected line_range array');
	} finally { cleanup(); clearActiveArtifact(); }
});
