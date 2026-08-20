/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Type checking stays ON (fail the build on type errors). ESLint is skipped
  // during build (no ESLint config in this minimal stack); `next lint` can be
  // added later.
  eslint: {
    ignoreDuringBuilds: true,
  },
  // All environment access must go through the NEXT_PUBLIC_* indirection in
  // src/lib/env.ts — never read process.env ad hoc in components.
};

export default nextConfig;
