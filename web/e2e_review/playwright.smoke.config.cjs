// A bounded PR selection; retain both servers because production CSP is a required sentinel.
const config = require("./playwright.config.cjs");
module.exports = {
  ...config,
  grep: /E1\/W1:|deep link \/settings |E9:|E3\/W19\/W7:|E16:|W26\/E19:|the preview serves the strict|signed-out shell, focus rings|native coded-transcript dialog/,
};
