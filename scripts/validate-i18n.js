#!/usr/bin/env node

/**
 * Validates that all locale files have the same keys as the English source.
 * Fails CI if any keys are missing.
 *
 * Usage: node scripts/validate-i18n.js
 */

const fs = require('fs');
const path = require('path');

const NEXTJS_MESSAGES_DIR = path.join(__dirname, '../nextjs/messages');
const IOS_RESOURCES_DIR = path.join(__dirname, '../ios/WineShelfScanner/Resources');

let hasErrors = false;

// ============================================
// Next.js JSON validation
// ============================================

function getNestedKeys(obj, prefix = '') {
  let keys = [];
  for (const key of Object.keys(obj)) {
    const fullKey = prefix ? `${prefix}.${key}` : key;
    if (typeof obj[key] === 'object' && obj[key] !== null) {
      keys = keys.concat(getNestedKeys(obj[key], fullKey));
    } else {
      keys.push(fullKey);
    }
  }
  return keys.sort();
}

function validateNextjsMessages() {
  console.log('Validating Next.js message files...\n');

  const enPath = path.join(NEXTJS_MESSAGES_DIR, 'en.json');
  if (!fs.existsSync(enPath)) {
    console.error('❌ English source file not found: en.json');
    hasErrors = true;
    return;
  }

  const enMessages = JSON.parse(fs.readFileSync(enPath, 'utf-8'));
  const enKeys = getNestedKeys(enMessages);

  console.log(`  Source: en.json (${enKeys.length} keys)`);

  const localeFiles = fs.readdirSync(NEXTJS_MESSAGES_DIR)
    .filter(f => f.endsWith('.json') && f !== 'en.json');

  for (const file of localeFiles) {
    const localePath = path.join(NEXTJS_MESSAGES_DIR, file);
    const localeMessages = JSON.parse(fs.readFileSync(localePath, 'utf-8'));
    const localeKeys = getNestedKeys(localeMessages);

    const missingKeys = enKeys.filter(k => !localeKeys.includes(k));
    const extraKeys = localeKeys.filter(k => !enKeys.includes(k));

    if (missingKeys.length === 0 && extraKeys.length === 0) {
      console.log(`  ✓ ${file} (${localeKeys.length} keys)`);
    } else {
      hasErrors = true;
      console.log(`  ✗ ${file}`);
      if (missingKeys.length > 0) {
        console.log(`    Missing ${missingKeys.length} keys:`);
        missingKeys.forEach(k => console.log(`      - ${k}`));
      }
      if (extraKeys.length > 0) {
        console.log(`    Extra ${extraKeys.length} keys (not in en.json):`);
        extraKeys.forEach(k => console.log(`      + ${k}`));
      }
    }
  }
}

// ============================================
// iOS Localizable.strings validation
// ============================================

function parseStringsFile(content) {
  const keys = [];
  // Match "key" = "value"; pattern
  const regex = /^"([^"]+)"\s*=\s*"[^"]*";/gm;
  let match;
  while ((match = regex.exec(content)) !== null) {
    keys.push(match[1]);
  }
  return keys.sort();
}

function validateiOSStrings() {
  console.log('\nValidating iOS Localizable.strings files...\n');

  const enPath = path.join(IOS_RESOURCES_DIR, 'en.lproj/Localizable.strings');
  if (!fs.existsSync(enPath)) {
    console.error('❌ English source file not found: en.lproj/Localizable.strings');
    hasErrors = true;
    return;
  }

  const enContent = fs.readFileSync(enPath, 'utf-8');
  const enKeys = parseStringsFile(enContent);

  console.log(`  Source: en.lproj (${enKeys.length} keys)`);

  const localeDirs = fs.readdirSync(IOS_RESOURCES_DIR)
    .filter(d => d.endsWith('.lproj') && d !== 'en.lproj');

  for (const dir of localeDirs) {
    const stringsPath = path.join(IOS_RESOURCES_DIR, dir, 'Localizable.strings');
    if (!fs.existsSync(stringsPath)) {
      console.log(`  ✗ ${dir} - Localizable.strings not found`);
      hasErrors = true;
      continue;
    }

    const localeContent = fs.readFileSync(stringsPath, 'utf-8');
    const localeKeys = parseStringsFile(localeContent);

    const missingKeys = enKeys.filter(k => !localeKeys.includes(k));
    const extraKeys = localeKeys.filter(k => !enKeys.includes(k));

    if (missingKeys.length === 0 && extraKeys.length === 0) {
      console.log(`  ✓ ${dir} (${localeKeys.length} keys)`);
    } else {
      hasErrors = true;
      console.log(`  ✗ ${dir}`);
      if (missingKeys.length > 0) {
        console.log(`    Missing ${missingKeys.length} keys:`);
        missingKeys.forEach(k => console.log(`      - ${k}`));
      }
      if (extraKeys.length > 0) {
        console.log(`    Extra ${extraKeys.length} keys (not in en.lproj):`);
        extraKeys.forEach(k => console.log(`      + ${k}`));
      }
    }
  }
}

// ============================================
// Main
// ============================================

console.log('🌐 i18n Validation\n');
console.log('='.repeat(50));

validateNextjsMessages();
validateiOSStrings();

console.log('\n' + '='.repeat(50));

if (hasErrors) {
  console.log('\n❌ Validation failed. Please fix missing/extra keys.\n');
  process.exit(1);
} else {
  console.log('\n✅ All locale files are in sync!\n');
  process.exit(0);
}
