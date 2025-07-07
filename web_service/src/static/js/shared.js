/* * Shared JavaScript functions for ScanSync
 * This file contains utility functions used across different templates.
 */

/* exported getContrastYIQ */
function getContrastYIQ(hex) {
    // Ensure the hex code starts with a hash
    if (!/^#/.test(hex)) {
        console.warn(`Invalid hex color: ${hex}. Expected format is #RRGGBB or #RGB.`);
        return '#000'; // Default to black if invalid
    }
    const c = hex.replace(/^#/, '');
    const r = parseInt(c.substr(0,2),16);
    const g = parseInt(c.substr(2,2),16);
    const b = parseInt(c.substr(4,2),16);
    const yiq = (r*299 + g*587 + b*114) / 1000;
    // console.log(`YIQ value for color ${hex} is: ${yiq}`);
    return (yiq >= 128) ? '#000' : '#fff';
}