module.exports = {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        background: '#0A0F24',
        card: '#111633',
        accent: '#5B8CFF',
        accentHover: '#7BA3FF',
        success: '#51C878',
        danger: '#FF5A78',
        textPrimary: '#F4F6FF',
        textSecondary: '#A0A7C4'
      },
      boxShadow: {
        card: '0 12px 30px rgba(15, 23, 42, 0.4)'
      }
    }
  },
  plugins: []
};
