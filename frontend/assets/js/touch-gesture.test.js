import { test } from 'node:test';
import assert from 'node:assert/strict';
import { startedInEdgeZone, resolveSwipeDirection, isTap, SWIPE_EDGE_EXCLUDE_PX, SWIPE_THRESHOLD_PX } from './touch-gesture.js';

test('startedInEdgeZone: 왼쪽 가장자리 안쪽이면 true', () => {
  assert.equal(startedInEdgeZone(10, 0, 400), true);
});
test('startedInEdgeZone: 오른쪽 가장자리 안쪽이면 true', () => {
  assert.equal(startedInEdgeZone(395, 0, 400), true);
});
test('startedInEdgeZone: 가장자리 밖이면 false', () => {
  assert.equal(startedInEdgeZone(200, 0, 400), false);
});
test('startedInEdgeZone: 경계값(edgePx 정확히)은 false', () => {
  assert.equal(startedInEdgeZone(SWIPE_EDGE_EXCLUDE_PX, 0, 400), false);
});

test('resolveSwipeDirection: 왼쪽으로 스와이프하면 다음(1)', () => {
  assert.equal(resolveSwipeDirection({ dx: -100, dy: 0, startedInEdge: false }), 1);
});
test('resolveSwipeDirection: 오른쪽으로 스와이프하면 이전(-1)', () => {
  assert.equal(resolveSwipeDirection({ dx: 100, dy: 0, startedInEdge: false }), -1);
});
test('resolveSwipeDirection: 가장자리에서 시작하면 무시(0)', () => {
  assert.equal(resolveSwipeDirection({ dx: -100, dy: 0, startedInEdge: true }), 0);
});
test('resolveSwipeDirection: threshold 미만이면 무시(0)', () => {
  assert.equal(resolveSwipeDirection({ dx: 30, dy: 0, startedInEdge: false }), 0);
});
test('resolveSwipeDirection: threshold 경계값(정확히 같음)은 무시(0)', () => {
  assert.equal(resolveSwipeDirection({ dx: SWIPE_THRESHOLD_PX, dy: 0, startedInEdge: false }), 0);
});
test('resolveSwipeDirection: 세로 이동이 더 크면 무시(0)', () => {
  assert.equal(resolveSwipeDirection({ dx: 60, dy: 80, startedInEdge: false }), 0);
});
test('resolveSwipeDirection: 가로/세로 이동이 같으면 무시(0)', () => {
  assert.equal(resolveSwipeDirection({ dx: 60, dy: -60, startedInEdge: false }), 0);
});

test('isTap: 짧은 움직임 + 빠른 시간은 tap', () => {
  assert.equal(isTap(5, 5, 100), true);
});
test('isTap: 움직임이 크면 tap 아님', () => {
  assert.equal(isTap(50, 0, 100), false);
});
test('isTap: 시간이 오래 걸리면 tap 아님', () => {
  assert.equal(isTap(5, 5, 500), false);
});
