const fs = require('fs');
const path = require('path');
const base = 'E:/AI/db/base';

// Analyze data quality
const stats = {
  totalFiles: 0,
  emptyProvides: 0,
  emptyRequires: 0,
  emptyUses: 0,
  emptyClasses: 0,
  emptyFields: 0,
  emptyMethods: 0,
  emptyTags: 0,
  byRole: {},
  byLayer: {},
  byGenre: {},
  byMajorTag: {},
  byMinorTag: {},
  avgProvides: 0,
  avgRequires: 0,
  avgUses: 0,
  avgMethods: 0,
  avgFields: 0
};

let totalProvides = 0, totalRequires = 0, totalUses = 0, totalMethods = 0, totalFields = 0;

for (const genre of fs.readdirSync(base)) {
  const gp = path.join(base, genre);
  if (!fs.statSync(gp).isDirectory()) continue;
  for (const layer of fs.readdirSync(gp)) {
    const filesPath = path.join(gp, layer, 'files');
    if (!fs.existsSync(filesPath)) continue;

    for (const file of fs.readdirSync(filesPath)) {
      if (!file.endsWith('.json')) continue;
      const data = JSON.parse(fs.readFileSync(path.join(filesPath, file)));
      stats.totalFiles++;

      // Track counts
      stats.byGenre[data.genre] = (stats.byGenre[data.genre] || 0) + 1;
      stats.byLayer[data.layer] = (stats.byLayer[data.layer] || 0) + 1;
      stats.byRole[data.role] = (stats.byRole[data.role] || 0) + 1;

      // Quality checks
      if (!data.provides || data.provides.length === 0) stats.emptyProvides++;
      if (!data.requires || data.requires.length === 0) stats.emptyRequires++;
      if (!data.uses || data.uses.length === 0) stats.emptyUses++;
      if (!data.classes || data.classes.length === 0) stats.emptyClasses++;

      // Tag checks
      if (!data.tags || (!data.tags.major?.length && !data.tags.minor?.length)) {
        stats.emptyTags++;
      } else {
        if (data.tags.major) {
          for (const t of data.tags.major) stats.byMajorTag[t] = (stats.byMajorTag[t] || 0) + 1;
        }
        if (data.tags.minor) {
          for (const t of data.tags.minor) stats.byMinorTag[t] = (stats.byMinorTag[t] || 0) + 1;
        }
      }

      totalProvides += (data.provides || []).length;
      totalRequires += (data.requires || []).length;
      totalUses += (data.uses || []).length;

      if (data.classes && data.classes[0]) {
        const cls = data.classes[0];
        if (!cls.methods || cls.methods.length === 0) stats.emptyMethods++;
        if (!cls.fields || cls.fields.length === 0) stats.emptyFields++;
        totalMethods += (cls.methods || []).length;
        totalFields += (cls.fields || []).length;
      }
    }
  }
}

stats.avgProvides = (totalProvides / stats.totalFiles).toFixed(1);
stats.avgRequires = (totalRequires / stats.totalFiles).toFixed(1);
stats.avgUses = (totalUses / stats.totalFiles).toFixed(1);
stats.avgMethods = (totalMethods / stats.totalFiles).toFixed(1);
stats.avgFields = (totalFields / stats.totalFiles).toFixed(1);

console.log('=== Data Quality Report (v3.0) ===');
console.log('Total files:', stats.totalFiles);
console.log('');
console.log('By Genre:', JSON.stringify(stats.byGenre));
console.log('By Layer:', JSON.stringify(stats.byLayer));

// All roles sorted
const allRoles = Object.entries(stats.byRole).sort((a,b)=>b[1]-a[1]);
console.log('By Role (all):', JSON.stringify(allRoles.reduce((o,[k,v])=>(o[k]=v,o),{})));
console.log('');
console.log('Empty provides:', stats.emptyProvides, '(' + (stats.emptyProvides/stats.totalFiles*100).toFixed(1) + '%)');
console.log('Empty requires:', stats.emptyRequires, '(' + (stats.emptyRequires/stats.totalFiles*100).toFixed(1) + '%)');
console.log('Empty uses:', stats.emptyUses, '(' + (stats.emptyUses/stats.totalFiles*100).toFixed(1) + '%)');
console.log('Empty methods:', stats.emptyMethods, '(' + (stats.emptyMethods/stats.totalFiles*100).toFixed(1) + '%)');
console.log('Empty fields:', stats.emptyFields, '(' + (stats.emptyFields/stats.totalFiles*100).toFixed(1) + '%)');
console.log('Empty tags:', stats.emptyTags, '(' + (stats.emptyTags/stats.totalFiles*100).toFixed(1) + '%)');
console.log('');
console.log('Avg provides per file:', stats.avgProvides);
console.log('Avg requires per file:', stats.avgRequires);
console.log('Avg uses per file:', stats.avgUses);
console.log('Avg methods per file:', stats.avgMethods);
console.log('Avg fields per file:', stats.avgFields);
console.log('');
const majorTags = Object.entries(stats.byMajorTag).sort((a,b)=>b[1]-a[1]);
console.log('By Major Tag:', JSON.stringify(majorTags.reduce((o,[k,v])=>(o[k]=v,o),{})));
const minorTags = Object.entries(stats.byMinorTag).sort((a,b)=>b[1]-a[1]);
console.log('By Minor Tag:', JSON.stringify(minorTags.reduce((o,[k,v])=>(o[k]=v,o),{})));
