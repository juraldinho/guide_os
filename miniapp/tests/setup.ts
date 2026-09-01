import '@testing-library/jest-dom/vitest';

// jsdom may omit or stub scrollIntoView incorrectly; Feed positions today on mount.
Element.prototype.scrollIntoView = function scrollIntoView() {};
