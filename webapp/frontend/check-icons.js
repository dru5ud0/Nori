const l = require('lucide-react');
const keys = Object.keys(l);
const linked = keys.filter(k => k.toLowerCase().includes('linked'));
console.log(linked.join(', '));