// این فایل فقط برای نمایش و گیم‌پلی سمت کلاینت است.
// پاداش نهایی (سکه/XP/جم) همیشه توسط سرور و مستقل از این مقادیر محاسبه می‌شود.
const ENEMY_TYPES = {
  slime:    { hp: 20,  speed: 60,  damage: 5,  xp: 2,   coins: 1, color: 0x4caf50, radius: 14, minWave: 1 },
  zombie:   { hp: 40,  speed: 50,  damage: 8,  xp: 4,   coins: 2, color: 0x8bc34a, radius: 16, minWave: 1 },
  skeleton: { hp: 35,  speed: 80,  damage: 10, xp: 6,   coins: 3, color: 0xe0e0e0, radius: 15, minWave: 2 },
  orc:      { hp: 70,  speed: 45,  damage: 14, xp: 9,   coins: 5, color: 0x795548, radius: 20, minWave: 3 },
  demon:    { hp: 100, speed: 70,  damage: 18, xp: 14,  coins: 8, color: 0xd32f2f, radius: 22, minWave: 5 },
  dragon:   { hp: 160, speed: 55,  damage: 25, xp: 25,  coins: 15, color: 0x9c27b0, radius: 26, minWave: 7 },
  boss:     { hp: 900, speed: 40,  damage: 35, xp: 120, coins: 90, gems: 5, color: 0xff5722, radius: 46, minWave: 5 },
};

const BOSS_WAVE_INTERVAL = 5;

const UPGRADE_POOL = [
  { id: "damage",     label: "+20% Damage",        icon: "⚔️", apply: (p) => p.damageMult *= 1.20 },
  { id: "atkspeed",   label: "+15% Attack Speed",   icon: "⚡", apply: (p) => p.attackSpeedMult *= 1.15 },
  { id: "movespeed",  label: "+10% Move Speed",     icon: "🏃", apply: (p) => p.moveSpeedMult *= 1.10 },
  { id: "doubleshot", label: "Double Shot",         icon: "🎯", apply: (p) => p.extraProjectiles += 1 },
  { id: "fire",       label: "Fire Bullet",         icon: "🔥", apply: (p) => p.element = "fire" },
  { id: "ice",        label: "Ice Bullet",          icon: "❄️", apply: (p) => p.element = "ice" },
  { id: "lightning",  label: "Lightning",           icon: "⛈️", apply: (p) => p.element = "lightning" },
  { id: "crit",       label: "+10% Critical Chance", icon: "💥", apply: (p) => p.critChance = Math.min(0.75, p.critChance + 0.10) },
  { id: "maxhp",      label: "+20 Max HP",          icon: "❤️", apply: (p) => { p.hpMax += 20; p.hp += 20; } },
  { id: "range",      label: "+15% Attack Range",   icon: "📡", apply: (p) => p.rangeMult *= 1.15 },
];

function pickRandomUpgrades(count) {
  const pool = [...UPGRADE_POOL];
  const picked = [];
  while (picked.length < count && pool.length > 0) {
    const i = Math.floor(Math.random() * pool.length);
    picked.push(pool.splice(i, 1)[0]);
  }
  return picked;
}