/**
 * root ⑤ (run_5e604f45): remote-image exfil guard in resolveImageSrc.
 *
 * The chat markdown renderer must NOT auto-fetch a remote image — a `![](https://evil/x.png)`
 * in message/requirement text would make the CSP=null webview GET an external URL on display
 * (tracking-pixel / data-exfil, no click). resolveImageSrc is the load-bearing component-level
 * drop: remote http(s) host → undefined (React omits src → no fetch); local/relative/data kept.
 *
 * These assert the SECURITY contract + the Gate-1 bypass/crash vectors (exact host match,
 * fail-closed on malformed URL).
 */
import { describe, it, expect, vi } from 'vitest';

// getApiBaseUrl is called for the local-resolve branch; stub to a stable desktop base.
vi.mock('../../../services/tauri', () => ({
  getApiBaseUrl: () => 'http://localhost:18321',
}));
// MarkdownRenderer imports a few UI-only deps at module load; stub the heavy ones so the
// pure function can be imported in a jsdom-free unit test.
vi.mock('mermaid', () => ({ default: { initialize: vi.fn(), render: vi.fn() } }));
vi.mock('highlight.js', () => ({ default: { highlightElement: vi.fn() } }));

import { resolveImageSrc } from '../MarkdownRenderer';

describe('resolveImageSrc — remote-image exfil guard (root ⑤)', () => {
  describe('DROPS remote http(s) hosts (exfil vector) → undefined', () => {
    it.each([
      'https://evil.example/track.png',
      'http://tracker.com/pixel.gif',
      'https://192.0.2.1/x.png',
      // bypass attempts — exact host match must reject all of these
      'https://localhost.evil.com/x.png',   // startsWith localhost but remote
      'https://localhost@evil.com/x.png',    // userinfo trick → host is evil.com
      'http://127.0.0.1.evil.com/x.png',     // 127.0.0.1 prefix but remote
      'HtTpS://EVIL.EXAMPLE/x.png',          // case
    ])('drops %s', (src) => {
      expect(resolveImageSrc(src)).toBeUndefined();
    });
  });

  describe('KEEPS local images', () => {
    it('keeps exact localhost (any port)', () => {
      expect(resolveImageSrc('http://localhost:18321/api/workspace/file/raw?path=a.png'))
        .toBe('http://localhost:18321/api/workspace/file/raw?path=a.png');
      expect(resolveImageSrc('http://localhost:1420/x.png')).toBe('http://localhost:1420/x.png');
    });
    it('keeps exact 127.0.0.1', () => {
      expect(resolveImageSrc('http://127.0.0.1:8000/x.png')).toBe('http://127.0.0.1:8000/x.png');
    });
    it('normalizes case for localhost', () => {
      expect(resolveImageSrc('HtTp://LOCALHOST:18321/x.png')).toBe('HtTp://LOCALHOST:18321/x.png');
    });
    it('keeps data: and blob:', () => {
      expect(resolveImageSrc('data:image/png;base64,iVBOR')).toBe('data:image/png;base64,iVBOR');
      expect(resolveImageSrc('blob:http://localhost/abc')).toBe('blob:http://localhost/abc');
    });
  });

  describe('relative / absolute workspace paths resolve to the local API (unchanged)', () => {
    it('resolves a relative path against basePath to the local raw-file endpoint', () => {
      const r = resolveImageSrc('images/foo.png', 'Projects/X/docs');
      expect(r).toContain('http://localhost:18321/api/workspace/file/raw');
      expect(r).toContain(encodeURIComponent('Projects/X/docs/images/foo.png'));
    });
    it('chat path (basePath undefined) returns a bare relative src unchanged (local, no fetch risk)', () => {
      // relative path with no base context: returned as-is; it is NOT a remote URL, cannot exfil.
      expect(resolveImageSrc('images/foo.png')).toBe('images/foo.png');
    });
    it('protocol-relative //evil is NOT an exfil hole — becomes an ENCODED local-daemon query, never an external fetch', () => {
      const r = resolveImageSrc('//evil.com/x.png');
      // `//evil.com` starts with '/' so it does NOT match the http(s) branch; it falls to
      // the local-resolve branch and is URL-ENCODED into the daemon raw-file endpoint
      // (the daemon 404s it). The webview NEVER fetches evil.com. (Gate-1 cleared this.)
      expect(r).toContain('http://localhost:18321/api/workspace/file/raw');
      expect(r).toContain(encodeURIComponent('//evil.com/x.png'));
      expect(r).not.toBe('//evil.com/x.png');
    });
  });

  describe('FAIL-CLOSED on malformed URL (Gate-1 BLOCKING — no throw into render)', () => {
    it.each([
      'https:// evil',       // space → new URL throws
      'https://',            // empty host
      'http://[',            // malformed bracket
    ])('drops malformed %s without throwing', (src) => {
      expect(() => resolveImageSrc(src)).not.toThrow();
      expect(resolveImageSrc(src)).toBeUndefined();
    });
  });

  it('passes falsy src through unchanged', () => {
    expect(resolveImageSrc(undefined)).toBeUndefined();
    expect(resolveImageSrc('')).toBe('');
  });

  describe('override/file-preview path (basePath defined) ALSO drops remote (L-1: lock branch ordering)', () => {
    // The http(s)-host check must run BEFORE the basePath resolve, so a remote URL is dropped
    // even in file preview. This negative test locks the ordering — a future refactor that
    // moved the basePath block above the host check would silently reopen the exfil hole in
    // previews, and this test would catch it.
    it('drops a remote image even when basePath is provided', () => {
      expect(resolveImageSrc('https://evil.example/x.png', 'Projects/X/docs')).toBeUndefined();
    });
    it('still resolves a relative local image when basePath is provided', () => {
      expect(resolveImageSrc('images/foo.png', 'Projects/X/docs'))
        .toContain('http://localhost:18321/api/workspace/file/raw');
    });
  });
});
