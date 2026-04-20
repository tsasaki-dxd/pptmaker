import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        purple: {
          DEFAULT: '#8B7AB8',
          lt: '#D9D1E8',
          dk: '#6B5C96',
          bg: '#F5F2F9',
        },
        muted: '#9B98A6',
        dark: '#3A3A42',
      },
      fontFamily: {
        sans: ['Noto Sans JP', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
export default config;
