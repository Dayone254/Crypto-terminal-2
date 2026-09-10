/** @type {import('next').NextConfig} */
const API_TARGET = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const nextConfig = {
    env: {
        NEXT_PUBLIC_API_URL: API_TARGET,
    },
    async rewrites() {
        return [
            {
                source: "/api/v1/:path*",
                destination: `${API_TARGET}/api/v1/:path*`,
            },
        ];
    },
};

module.exports = nextConfig;
