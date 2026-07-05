// Jest setup file
import '@testing-library/jest-dom';

// jsdom doesn't provide TextEncoder/TextDecoder (needed by the SSE stream
// parser in api-client); polyfill from Node.
import { TextEncoder, TextDecoder } from 'util';
if (typeof global.TextEncoder === 'undefined') {
  (global as any).TextEncoder = TextEncoder;
}
if (typeof global.TextDecoder === 'undefined') {
  (global as any).TextDecoder = TextDecoder;
}
