import {defineConfig} from 'vite';
// Resolve shared presentation components against this application's pinned React.
export default defineConfig({resolve:{dedupe:['react','react-dom']}});
