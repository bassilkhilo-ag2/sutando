/**
 * Unit tests for src/meeting-tools.ts —
 * joinGmeetTool, lookupMeetingIdTool, callContactTool.
 *
 * joinGmeetTool.execute: only the early-exit (empty code) paths are tested —
 * the happy path calls execSync/open which would launch Chrome on the host.
 *
 * callContactTool.execute: skipped — first thing it does is execSync('open -ga
 * Contacts'), which would pop open Contacts.app. Metadata only.
 *
 * lookupMeetingIdTool.execute: fully tested via env var overrides.
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
	joinGmeetTool,
	lookupMeetingIdTool,
	callContactTool,
} from '../src/meeting-tools.ts';

type AnyRecord = Record<string, unknown>;

function clearZoomEnv() {
	delete process.env.ZOOM_PERSONAL_MEETING_ID;
	delete process.env.ZOOM_PERSONAL_PASSCODE;
	delete process.env.ZOOM_PASSCODE;
}

// ---------------------------------------------------------------------------
// Tool metadata
// ---------------------------------------------------------------------------

test('joinGmeetTool has name join_gmeet and execution inline', () => {
	assert.equal(joinGmeetTool.name, 'join_gmeet');
	assert.equal(joinGmeetTool.execution, 'inline');
});

test('joinGmeetTool description mentions Google Meet', () => {
	assert.ok(
		joinGmeetTool.description.toLowerCase().includes('google meet'),
		`Expected "google meet" in description: ${joinGmeetTool.description}`,
	);
});

test('lookupMeetingIdTool has name lookup_meeting_id and execution inline', () => {
	assert.equal(lookupMeetingIdTool.name, 'lookup_meeting_id');
	assert.equal(lookupMeetingIdTool.execution, 'inline');
});

test('lookupMeetingIdTool description mentions Zoom and meeting ID', () => {
	const d = lookupMeetingIdTool.description.toLowerCase();
	assert.ok(d.includes('zoom'), `Expected "zoom" in description`);
	assert.ok(d.includes('meeting id') || d.includes('meeting_id'), `Expected "meeting id" in description`);
});

test('callContactTool has name call_contact and execution inline', () => {
	assert.equal(callContactTool.name, 'call_contact');
	assert.equal(callContactTool.execution, 'inline');
});

test('callContactTool description mentions phone call and contacts', () => {
	const d = callContactTool.description.toLowerCase();
	assert.ok(d.includes('call'), `Expected "call" in description`);
	assert.ok(d.includes('contact'), `Expected "contact" in description`);
});

// ---------------------------------------------------------------------------
// joinGmeetTool — early-exit paths (no execSync called)
// ---------------------------------------------------------------------------

test('joinGmeetTool returns error for empty string meetingCode', async () => {
	const result = await (joinGmeetTool.execute as (a: AnyRecord) => Promise<AnyRecord>)({ meetingCode: '' });
	assert.ok('error' in result, `Expected error, got: ${JSON.stringify(result)}`);
});

test('joinGmeetTool returns error for bare base URL (no code)', async () => {
	// After stripping the prefix, code becomes '' → early return
	const result = await (joinGmeetTool.execute as (a: AnyRecord) => Promise<AnyRecord>)({
		meetingCode: 'https://meet.google.com/',
	});
	assert.ok('error' in result, `Expected error, got: ${JSON.stringify(result)}`);
});

test('joinGmeetTool returns error for whitespace-only meetingCode', async () => {
	const result = await (joinGmeetTool.execute as (a: AnyRecord) => Promise<AnyRecord>)({ meetingCode: '   ' });
	assert.ok('error' in result, `Expected error, got: ${JSON.stringify(result)}`);
});

// ---------------------------------------------------------------------------
// lookupMeetingIdTool — fully testable via env
// ---------------------------------------------------------------------------

test('lookupMeetingIdTool returns error when ZOOM_PERSONAL_MEETING_ID not set', async () => {
	clearZoomEnv();
	try {
		const result = await (lookupMeetingIdTool.execute as (a: AnyRecord) => Promise<AnyRecord>)({});
		assert.ok('error' in result, `Expected error, got: ${JSON.stringify(result)}`);
	} finally {
		clearZoomEnv();
	}
});

test('lookupMeetingIdTool returns meetingId when env var is set', async () => {
	clearZoomEnv();
	process.env.ZOOM_PERSONAL_MEETING_ID = '123-456-7890';
	try {
		const result = await (lookupMeetingIdTool.execute as (a: AnyRecord) => Promise<AnyRecord>)({});
		assert.equal(result.meetingId, '123-456-7890');
		assert.equal(result.source, 'ZOOM_PERSONAL_MEETING_ID from .env');
	} finally {
		clearZoomEnv();
	}
});

test('lookupMeetingIdTool returns null passcode when neither passcode env var is set', async () => {
	clearZoomEnv();
	process.env.ZOOM_PERSONAL_MEETING_ID = '111-222-3333';
	try {
		const result = await (lookupMeetingIdTool.execute as (a: AnyRecord) => Promise<AnyRecord>)({});
		assert.equal(result.passcode, null);
	} finally {
		clearZoomEnv();
	}
});

test('lookupMeetingIdTool returns ZOOM_PERSONAL_PASSCODE when set', async () => {
	clearZoomEnv();
	process.env.ZOOM_PERSONAL_MEETING_ID = '111-222-3333';
	process.env.ZOOM_PERSONAL_PASSCODE = 'secret123';
	try {
		const result = await (lookupMeetingIdTool.execute as (a: AnyRecord) => Promise<AnyRecord>)({});
		assert.equal(result.passcode, 'secret123');
	} finally {
		clearZoomEnv();
	}
});

test('lookupMeetingIdTool falls back to ZOOM_PASSCODE when ZOOM_PERSONAL_PASSCODE unset', async () => {
	clearZoomEnv();
	process.env.ZOOM_PERSONAL_MEETING_ID = '111-222-3333';
	process.env.ZOOM_PASSCODE = 'fallback456';
	try {
		const result = await (lookupMeetingIdTool.execute as (a: AnyRecord) => Promise<AnyRecord>)({});
		assert.equal(result.passcode, 'fallback456');
	} finally {
		clearZoomEnv();
	}
});

test('lookupMeetingIdTool ZOOM_PERSONAL_PASSCODE takes priority over ZOOM_PASSCODE', async () => {
	clearZoomEnv();
	process.env.ZOOM_PERSONAL_MEETING_ID = '111-222-3333';
	process.env.ZOOM_PERSONAL_PASSCODE = 'primary';
	process.env.ZOOM_PASSCODE = 'fallback';
	try {
		const result = await (lookupMeetingIdTool.execute as (a: AnyRecord) => Promise<AnyRecord>)({});
		assert.equal(result.passcode, 'primary');
	} finally {
		clearZoomEnv();
	}
});

test('lookupMeetingIdTool instruction mentions passcode when set', async () => {
	clearZoomEnv();
	process.env.ZOOM_PERSONAL_MEETING_ID = '111-222-3333';
	process.env.ZOOM_PERSONAL_PASSCODE = 'mypasscode';
	try {
		const result = await (lookupMeetingIdTool.execute as (a: AnyRecord) => Promise<AnyRecord>)({});
		assert.ok(
			(result.instruction as string).includes('Passcode'),
			`Expected passcode mention in instruction: ${result.instruction}`,
		);
	} finally {
		clearZoomEnv();
	}
});

test('lookupMeetingIdTool instruction says no passcode when none set', async () => {
	clearZoomEnv();
	process.env.ZOOM_PERSONAL_MEETING_ID = '111-222-3333';
	try {
		const result = await (lookupMeetingIdTool.execute as (a: AnyRecord) => Promise<AnyRecord>)({});
		assert.ok(
			(result.instruction as string).toLowerCase().includes('no passcode'),
			`Expected "no passcode" in instruction: ${result.instruction}`,
		);
	} finally {
		clearZoomEnv();
	}
});
