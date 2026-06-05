// Regression guard for the skill-loader last-write-wins dedup (#1467 fix).
//
// Root cause: loadSkillManifestTools() scanned both ~/Projects/sutando/skills/
// and ~/.sutando/workspace/skills/. Both had a screen-companion skill with an
// activate_screen_companion tool, so the same name appeared twice in the
// assembled tool list. assertUniqueToolNames() threw at module-load time,
// crashing every test that imported from inline-tools.js.
//
// Fix: switch from array.push(...mod.tools) to Map-based dedup (last-write-wins
// per the existing comment "last-write-wins for same-name skills"). The Map
// dedups before assertUniqueToolNames() ever runs, so even overlapping skill
// directories no longer cause a crash.
//
// This test is STRUCTURAL — it reads the source and asserts the dedup pattern
// is present, without dynamically importing the module (which would trigger
// real skill-directory scans, audio/screen state, etc.). Structural tests are
// the correct approach for catching "someone reverted the dedup to push()" regressions
// while keeping the test fast and side-effect-free.

import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO = join(dirname(fileURLToPath(import.meta.url)), '..');
const INLINE_TOOLS_SRC = readFileSync(join(REPO, 'src', 'inline-tools.ts'), 'utf8');

describe('skill-loader dedup (regression: duplicate tool name crash)', () => {
	test('loadSkillManifestTools uses Map for last-write-wins dedup, not bare array push', () => {
		// The old code: `(tier === 'any_caller' ? anyCaller : owner).push(...mod.tools)`
		// The new code: uses ownerMap/anyCallerMap with .set() per tool.
		// Guard: if someone reverts to the bare push, this test catches it.
		assert.ok(
			INLINE_TOOLS_SRC.includes('ownerMap') && INLINE_TOOLS_SRC.includes('anyCallerMap'),
			'loadSkillManifestTools must declare ownerMap and anyCallerMap for dedup'
		);
		assert.ok(
			INLINE_TOOLS_SRC.includes('target.set(tool.name, tool)'),
			'dedup must use Map.set() keyed on tool.name (last-write-wins)'
		);
		// Ensure the old bare-push pattern is gone.
		assert.ok(
			!INLINE_TOOLS_SRC.includes('owner).push(...mod.tools)') &&
			!INLINE_TOOLS_SRC.includes('anyCaller).push(...mod.tools)'),
			'bare push(...mod.tools) must NOT be present — dedup would be skipped'
		);
	});

	test('return statement converts Maps back to arrays', () => {
		// Final return must spread the Map values, not return the Maps themselves.
		assert.ok(
			INLINE_TOOLS_SRC.includes('[...ownerMap.values()]') &&
			INLINE_TOOLS_SRC.includes('[...anyCallerMap.values()]'),
			'return value must spread Map values to ToolDefinition[] arrays'
		);
	});

	test('assertUniqueToolNames is still present as belt-and-suspenders', () => {
		// The dedup Map prevents duplicates within skill-loader, but
		// assertUniqueToolNames provides a hard stop if other code paths
		// (e.g. inline tool registration) introduce a duplicate downstream.
		assert.ok(
			INLINE_TOOLS_SRC.includes('function assertUniqueToolNames'),
			'assertUniqueToolNames guard must remain in inline-tools.ts'
		);
		assert.ok(
			INLINE_TOOLS_SRC.includes('assertUniqueToolNames(['),
			'assertUniqueToolNames must still be called when building the final tool list'
		);
	});

	test('overwriting log message present (aids debugging duplicate-skill installs)', () => {
		// When a later dir overwrites an earlier dir's tool, the loader logs it.
		// This makes "why did my skill disappear?" debuggable without source diving.
		assert.ok(
			INLINE_TOOLS_SRC.includes("overwriting '"),
			'skill-loader must log when a tool is overwritten by a later skill dir'
		);
	});
});
