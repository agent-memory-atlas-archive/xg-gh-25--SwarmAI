/**
 * root ⑤ Layer-4 cross-boundary E2E (run_5e604f45): drive the REAL MarkdownRenderer
 * component with a markdown remote image and assert the rendered <img> carries NO
 * external src — the full seam from markdown text → react-markdown v10 → the base img
 * component → resolveImageSrc → DOM. This is the actual exfil surface (chat), not a
 * unit of the resolver in isolation.
 *
 * Mutation-proof: if the base img component were reverted to src={src} (the exfil
 * bypass), the rendered <img> would carry src="https://evil..." → this test goes RED.
 */
import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';

vi.mock('../../../services/tauri', () => ({ getApiBaseUrl: () => 'http://localhost:18321' }));
vi.mock('mermaid', () => ({ default: { initialize: vi.fn(), render: vi.fn() } }));
vi.mock('highlight.js', () => ({ default: { highlightElement: vi.fn(), configure: vi.fn() } }));
// ThemeContext + clipboard + openExternal are pulled in transitively; stub to no-ops.
vi.mock('../../../contexts/ThemeContext', () => ({ useTheme: () => ({ resolvedTheme: 'light' }) }));
vi.mock('../../../utils/clipboard', () => ({ copyToClipboard: vi.fn() }));
vi.mock('../../../utils/openExternal', () => ({ openExternal: vi.fn() }));

import MarkdownRenderer from '../MarkdownRenderer';

describe('MarkdownRenderer — remote image E2E (root ⑤, chat path)', () => {
  it('a chat markdown remote image renders an <img> with NO external src (no fetch)', () => {
    // basePath undefined = the CHAT path (base img component)
    const { container } = render(
      <MarkdownRenderer content={'before ![pixel](https://evil.example/track.png) after'} />,
    );
    const img = container.querySelector('img');
    expect(img).not.toBeNull();
    // The src attribute must NOT be the external URL. resolveImageSrc returns undefined
    // → React omits the attribute → img.getAttribute('src') is null.
    const src = img!.getAttribute('src');
    // resolveImageSrc returns undefined for a remote host → React omits the attr → null.
    expect(src == null || src === '').toBe(true);
    expect(src ?? '').not.toContain('evil.example');
  });

  it('a chat markdown LOCAL (localhost) image keeps its src', () => {
    const { container } = render(
      <MarkdownRenderer content={'![ok](http://localhost:18321/api/workspace/file/raw?path=a.png)'} />,
    );
    const img = container.querySelector('img');
    expect(img!.getAttribute('src')).toBe('http://localhost:18321/api/workspace/file/raw?path=a.png');
  });

  it('a malformed remote image does not throw / blank the render', () => {
    expect(() =>
      render(<MarkdownRenderer content={'![x](https:// evil)'} />),
    ).not.toThrow();
  });
});
