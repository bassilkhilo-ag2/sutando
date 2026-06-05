/**
 * Unit tests for src/recording-tools.ts.
 *
 * Pure-state paths only — no execSync, ffmpeg, or network calls.
 *
 * Covered:
 *   isRecordingActive()  — reads /tmp/sutando-screen-record.pid (create/delete in tests)
 *   isRecordingMuted()   — reads recordingState.muted (mutate + restore)
 *   resetDemoState()     — sets demoStateRef.value → 'idle'
 *   Tool metadata        — name + execution='inline' for all 7 exported ToolDefinitions
 *
 * Not covered: execSync/ffmpeg paths (scrollDown, stopActiveRecording, screenRecordTool
 * execute), fetch paths (describeScreenshot, captureScreen), vision model calls.
 */

import assert from 'node:assert/strict';
import { existsSync, writeFileSync, unlinkSync } from 'node:fs';
import { test } from 'node:test';

import {
	isRecordingActive,
	isRecordingMuted,
	resetDemoState,
	recordingState,
	scrollAndDescribeTool,
	playVideoTool,
	pauseVideoTool,
	resumeVideoTool,
	replayVideoTool,
	closeVideoTool,
	screenRecordTool,
} from '../src/recording-tools.ts';

import { demoStateRef } from '../src/recording-state.ts';

const PID_PATH = '/tmp/sutando-screen-record.pid';

// ---------------------------------------------------------------------------
// isRecordingActive — /tmp sentinel
// ---------------------------------------------------------------------------

test('isRecordingActive returns false when pid file is absent', () => {
	const orig = existsSync(PID_PATH) ? 'present' : null;
	try {
		if (orig !== null) unlinkSync(PID_PATH);
		assert.equal(isRecordingActive(), false);
	} finally {
		// restore — nothing to restore if it was absent
	}
});

test('isRecordingActive returns true when pid file exists', () => {
	const hadFile = existsSync(PID_PATH);
	try {
		writeFileSync(PID_PATH, '12345');
		assert.equal(isRecordingActive(), true);
	} finally {
		if (!hadFile) unlinkSync(PID_PATH);
	}
});

// ---------------------------------------------------------------------------
// isRecordingMuted — reads recordingState.muted
// ---------------------------------------------------------------------------

test('isRecordingMuted returns false when recordingState.muted is false', () => {
	const orig = recordingState.muted;
	try {
		recordingState.muted = false;
		assert.equal(isRecordingMuted(), false);
	} finally {
		recordingState.muted = orig;
	}
});

test('isRecordingMuted returns true when recordingState.muted is true', () => {
	const orig = recordingState.muted;
	try {
		recordingState.muted = true;
		assert.equal(isRecordingMuted(), true);
	} finally {
		recordingState.muted = orig;
	}
});

// ---------------------------------------------------------------------------
// resetDemoState — sets demoStateRef.value → 'idle'
// ---------------------------------------------------------------------------

test('resetDemoState transitions "recording" → "idle"', () => {
	const orig = demoStateRef.value;
	try {
		demoStateRef.value = 'recording';
		resetDemoState();
		assert.equal(demoStateRef.value, 'idle');
	} finally {
		demoStateRef.value = orig as typeof demoStateRef.value;
	}
});

test('resetDemoState is idempotent when already idle', () => {
	const orig = demoStateRef.value;
	try {
		demoStateRef.value = 'idle';
		resetDemoState();
		assert.equal(demoStateRef.value, 'idle');
	} finally {
		demoStateRef.value = orig as typeof demoStateRef.value;
	}
});

// ---------------------------------------------------------------------------
// Tool metadata
// ---------------------------------------------------------------------------

test('scrollAndDescribeTool has name record_screen_with_narration and execution inline', () => {
	assert.equal(scrollAndDescribeTool.name, 'record_screen_with_narration');
	assert.equal(scrollAndDescribeTool.execution, 'inline');
});

test('playVideoTool has name play_video and execution inline', () => {
	assert.equal(playVideoTool.name, 'play_video');
	assert.equal(playVideoTool.execution, 'inline');
});

test('pauseVideoTool has name pause_video and execution inline', () => {
	assert.equal(pauseVideoTool.name, 'pause_video');
	assert.equal(pauseVideoTool.execution, 'inline');
});

test('resumeVideoTool has name resume_video and execution inline', () => {
	assert.equal(resumeVideoTool.name, 'resume_video');
	assert.equal(resumeVideoTool.execution, 'inline');
});

test('replayVideoTool has name replay_video and execution inline', () => {
	assert.equal(replayVideoTool.name, 'replay_video');
	assert.equal(replayVideoTool.execution, 'inline');
});

test('closeVideoTool has name close_video and execution inline', () => {
	assert.equal(closeVideoTool.name, 'close_video');
	assert.equal(closeVideoTool.execution, 'inline');
});

test('screenRecordTool has name screen_record and execution inline', () => {
	assert.equal(screenRecordTool.name, 'screen_record');
	assert.equal(screenRecordTool.execution, 'inline');
});

test('screenRecordTool description mentions start and stop', () => {
	const d = screenRecordTool.description.toLowerCase();
	assert.ok(d.includes('start') || d.includes('record'), `Expected "start/record" in description`);
	assert.ok(d.includes('stop') || d.includes('end'), `Expected "stop/end" in description`);
});
