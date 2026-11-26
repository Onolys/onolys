// Radix (via @onolys/ui Checkbox) needs ResizeObserver, which jsdom lacks (same stand-in as web/src/test/setup.ts).
if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
