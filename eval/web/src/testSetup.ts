// Radix (via @onolys/common Checkbox) needs ResizeObserver, which jsdom lacks (same stand-in the shared package's tests use).
if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
