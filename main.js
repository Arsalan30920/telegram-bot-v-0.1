const WORLD_SIZE = 3000;
const HUD = {
  hpFill: null, xpFill: null, waveText: null, coinText: null, gemText: null, levelText: null,
};

let playerProfile = null; // از سرور می‌آید (سکه/جم/لول واقعی حساب)

class GameScene extends Phaser.Scene {
  constructor() {
    super("GameScene");
  }

  // ---------------- PRELOAD: ساخت بافت‌ها بدون فایل خارجی ----------------
  preload() {
    const g = this.make.graphics({ x: 0, y: 0, add: false });

    // بازیکن
    g.clear();
    g.fillStyle(0x29b6f6, 1);
    g.fillCircle(20, 20, 18);
    g.lineStyle(3, 0xffffff, 0.9);
    g.strokeCircle(20, 20, 18);
    g.generateTexture("player_tex", 40, 40);

    // گلوله معمولی
    g.clear();
    g.fillStyle(0xffee58, 1);
    g.fillCircle(6, 6, 6);
    g.generateTexture("bullet_tex", 12, 12);

    // گلوله آتشین
    g.clear();
    g.fillStyle(0xff7043, 1);
    g.fillCircle(6, 6, 6);
    g.generateTexture("bullet_fire", 12, 12);

    // گلوله یخی
    g.clear();
    g.fillStyle(0x4fc3f7, 1);
    g.fillCircle(6, 6, 6);
    g.generateTexture("bullet_ice", 12, 12);

    // گلوله رعد
    g.clear();
    g.fillStyle(0xba68c8, 1);
    g.fillCircle(6, 6, 6);
    g.generateTexture("bullet_lightning", 12, 12);

    // دشمن‌ها
    for (const [type, cfg] of Object.entries(ENEMY_TYPES)) {
      g.clear();
      g.fillStyle(cfg.color, 1);
      g.fillCircle(cfg.radius, cfg.radius, cfg.radius);
      g.lineStyle(2, 0x000000, 0.4);
      g.strokeCircle(cfg.radius, cfg.radius, cfg.radius);
      g.generateTexture(`enemy_${type}`, cfg.radius * 2, cfg.radius * 2);
    }

    // سکه
    g.clear();
    g.fillStyle(0xffd54f, 1);
    g.fillCircle(7, 7, 7);
    g.lineStyle(2, 0xffa000, 1);
    g.strokeCircle(7, 7, 7);
    g.generateTexture("coin_tex", 14, 14);

    // جم
    g.clear();
    g.fillStyle(0xab47bc, 1);
    g.fillRect(3, 0, 8, 8);
    g.generateTexture("gem_tex", 14, 14);

    // ذره افکت انفجار
    g.clear();
    g.fillStyle(0xffffff, 1);
    g.fillCircle(4, 4, 4);
    g.generateTexture("particle_tex", 8, 8);

    // زمینه (گرید ساده)
    g.clear();
    g.fillStyle(0x14161f, 1);
    g.fillRect(0, 0, 64, 64);
    g.lineStyle(1, 0x22263a, 1);
    g.strokeRect(0, 0, 64, 64);
    g.generateTexture("bg_tile", 64, 64);
  }

  // ---------------- CREATE ----------------
  create() {
    this.physics.world.setBounds(0, 0, WORLD_SIZE, WORLD_SIZE);
    this.add.tileSprite(0, 0, WORLD_SIZE, WORLD_SIZE, "bg_tile").setOrigin(0, 0);

    // بازیکن
    this.player = this.physics.add.sprite(WORLD_SIZE / 2, WORLD_SIZE / 2, "player_tex");
    this.player.setCollideWorldBounds(true);
    this.player.setDamping(true).setDrag(0.85);

    this.stats = {
      hpMax: playerProfile.hp_max || 100,
      hp: playerProfile.hp_max || 100,
      damageMult: 1,
      attackSpeedMult: 1,
      moveSpeedMult: 1,
      rangeMult: 1,
      extraProjectiles: 0,
      critChance: 0.05,
      element: null,
      baseDamage: 12,
      baseRange: 380,
      baseAttackIntervalMs: 550,
      baseMoveSpeed: 220,
    };

    this.sessionXP = 0;
    this.sessionLevel = 1;
    this.sessionCoins = 0;
    this.sessionGems = 0;
    this.killsByType = {};
    this.currentWave = 1;
    this.startTime = this.time.now;
    this.lastPlayerHitAt = 0;
    this.gameOver = false;

    // گروه‌ها
    this.enemies = this.physics.add.group();
    this.bullets = this.physics.add.group();
    this.loot = this.physics.add.group();

    this.cameras.main.startFollow(this.player, true, 0.12, 0.12);
    this.cameras.main.setBounds(0, 0, WORLD_SIZE, WORLD_SIZE);
    this.cameras.main.setZoom(1);

    // مینی‌مپ (دوربین دوم)
    this.minimapCam = this.cameras.add(
      window.innerWidth - 130, 16, 114, 114
    ).setZoom(0.05).setBounds(0, 0, WORLD_SIZE, WORLD_SIZE);
    this.minimapCam.startFollow(this.player);
    this.minimapCam.setBackgroundColor(0x0b0c12);

    // برخورد گلوله با دشمن
    this.physics.add.overlap(this.bullets, this.enemies, this.onBulletHitEnemy, null, this);
    // برخورد دشمن با بازیکن
    this.physics.add.overlap(this.player, this.enemies, this.onEnemyHitPlayer, null, this);
    // برداشتن لوت
    this.physics.add.overlap(this.player, this.loot, this.onCollectLoot, null, this);

    // تایمرها
    this.spawnEvent = this.time.addEvent({
      delay: 900,
      loop: true,
      callback: () => this.spawnLoop(),
    });

    this.attackEvent = this.time.addEvent({
      delay: this.stats.baseAttackIntervalMs,
      loop: true,
      callback: () => this.autoAttack(),
    });

    this.spawnWaveBatch(6);

    this.updateHUD();
  }

  // ---------------- WAVE / SPAWN ----------------
  spawnLoop() {
    if (this.gameOver) return;
    const elapsed = (this.time.now - this.startTime) / 1000;
    this.currentWave = 1 + Math.floor(elapsed / 30);

    const isBossWave = this.currentWave % BOSS_WAVE_INTERVAL === 0;
    if (isBossWave && !this.bossSpawnedForWave) {
      this.bossSpawnedForWave = this.currentWave;
      this.spawnEnemy("boss");
      this.flashBossWarning();
      return;
    }

    const countThisTick = 1 + Math.floor(this.currentWave / 3);
    for (let i = 0; i < countThisTick; i++) {
      this.spawnEnemy(this.pickEnemyTypeForWave());
    }
  }

  spawnWaveBatch(n) {
    for (let i = 0; i < n; i++) this.spawnEnemy(this.pickEnemyTypeForWave());
  }

  pickEnemyTypeForWave() {
    const available = Object.entries(ENEMY_TYPES).filter(
      ([type, cfg]) => type !== "boss" && cfg.minWave <= this.currentWave
    );
    const [type] = available[Math.floor(Math.random() * available.length)];
    return type;
  }

  spawnEnemy(type) {
    const cfg = ENEMY_TYPES[type];
    const angle = Math.random() * Math.PI * 2;
    const dist = 500 + Math.random() * 150;
    let x = this.player.x + Math.cos(angle) * dist;
    let y = this.player.y + Math.sin(angle) * dist;
    x = Phaser.Math.Clamp(x, 30, WORLD_SIZE - 30);
    y = Phaser.Math.Clamp(y, 30, WORLD_SIZE - 30);

    const waveScale = 1 + (this.currentWave - 1) * 0.12;
    const enemy = this.physics.add.sprite(x, y, `enemy_${type}`);
    enemy.enemyType = type;
    enemy.hp = Math.round(cfg.hp * waveScale);
    enemy.maxHp = enemy.hp;
    enemy.speed = cfg.speed;
    enemy.damage = Math.round(cfg.damage * (1 + (this.currentWave - 1) * 0.06));
    enemy.lastHitPlayerAt = 0;
    this.enemies.add(enemy);
  }

  flashBossWarning() {
    const txt = this.add.text(this.cameras.main.width / 2, 120, "⚠️ BOSS INCOMING ⚠️", {
      fontSize: "28px", color: "#ff5252", fontStyle: "bold",
    }).setScrollFactor(0).setOrigin(0.5).setDepth(1000);
    this.tweens.add({ targets: txt, alpha: 0, duration: 2000, delay: 800, onComplete: () => txt.destroy() });
  }

  // ---------------- ATTACK ----------------
  autoAttack() {
    if (this.gameOver) return;
    const range = this.stats.baseRange * this.stats.rangeMult;
    let nearest = null;
    let nearestDist = range;

    this.enemies.children.iterate((enemy) => {
      if (!enemy || !enemy.active) return;
      const d = Phaser.Math.Distance.Between(this.player.x, this.player.y, enemy.x, enemy.y);
      if (d < nearestDist) {
        nearestDist = d;
        nearest = enemy;
      }
    });

    if (!nearest) return;

    const shotsCount = 1 + this.stats.extraProjectiles;
    for (let i = 0; i < shotsCount; i++) {
      const spread = (i - (shotsCount - 1) / 2) * 0.15;
      this.fireBullet(nearest, spread);
    }
  }

  fireBullet(target, angleOffset) {
    const baseAngle = Phaser.Math.Angle.Between(this.player.x, this.player.y, target.x, target.y);
    const angle = baseAngle + angleOffset;

    let texKey = "bullet_tex";
    if (this.stats.element === "fire") texKey = "bullet_fire";
    else if (this.stats.element === "ice") texKey = "bullet_ice";
    else if (this.stats.element === "lightning") texKey = "bullet_lightning";

    const bullet = this.physics.add.sprite(this.player.x, this.player.y, texKey);
    bullet.element = this.stats.element;
    bullet.damage = this.stats.baseDamage * this.stats.damageMult;
    this.bullets.add(bullet);

    const speed = 520;
    bullet.setVelocity(Math.cos(angle) * speed, Math.sin(angle) * speed);
    this.time.delayedCall(1200, () => bullet.destroy());
  }

  onBulletHitEnemy(bullet, enemy) {
    if (!bullet.active || !enemy.active) return;

    let dmg = bullet.damage;
    let isCrit = Math.random() < this.stats.critChance;
    if (isCrit) dmg *= 2;

    enemy.hp -= dmg;
    this.showFloatingDamage(enemy.x, enemy.y, Math.round(dmg), isCrit);

    if (bullet.element === "ice") {
      enemy.speed = Math.max(10, enemy.speed * 0.5);
    } else if (bullet.element === "fire") {
      enemy.hp -= 3; // دمیج اضافه سوختگی
    } else if (bullet.element === "lightning") {
      this.chainLightning(enemy);
    }

    bullet.destroy();

    if (enemy.hp <= 0) {
      this.killEnemy(enemy);
    }
  }

  chainLightning(fromEnemy) {
    let closest = null;
    let closestDist = 160;
    this.enemies.children.iterate((e) => {
      if (!e || !e.active || e === fromEnemy) return;
      const d = Phaser.Math.Distance.Between(fromEnemy.x, fromEnemy.y, e.x, e.y);
      if (d < closestDist) {
        closestDist = d;
        closest = e;
      }
    });
    if (closest) {
      closest.hp -= 8;
      this.showFloatingDamage(closest.x, closest.y, 8, false);
      const line = this.add.line(0, 0, fromEnemy.x, fromEnemy.y, closest.x, closest.y, 0xba68c8, 0.8).setLineWidth(2);
      this.time.delayedCall(120, () => line.destroy());
      if (closest.hp <= 0) this.killEnemy(closest);
    }
  }

  killEnemy(enemy) {
    const type = enemy.enemyType;
    this.killsByType[type] = (this.killsByType[type] || 0) + 1;

    const cfg = ENEMY_TYPES[type];
    this.sessionXP += cfg.xp;
    this.spawnExplosion(enemy.x, enemy.y);
    this.maybeDropLoot(enemy.x, enemy.y, cfg);
    this.checkLevelUp();

    enemy.destroy();
    this.updateHUD();
  }

  spawnExplosion(x, y) {
    const particles = this.add.particles(x, y, "particle_tex", {
      speed: { min: 60, max: 180 },
      scale: { start: 1, end: 0 },
      lifespan: 350,
      quantity: 10,
      tint: 0xffffff,
    });
    this.time.delayedCall(360, () => particles.destroy());
  }

  showFloatingDamage(x, y, amount, isCrit) {
    const txt = this.add.text(x, y - 10, isCrit ? `${amount}!` : `${amount}`, {
      fontSize: isCrit ? "22px" : "16px",
      color: isCrit ? "#ff7043" : "#ffffff",
      fontStyle: "bold",
    }).setOrigin(0.5);
    this.tweens.add({
      targets: txt, y: y - 50, alpha: 0, duration: 700,
      onComplete: () => txt.destroy(),
    });
  }

  // ---------------- LOOT ----------------
  maybeDropLoot(x, y, cfg) {
    if (Math.random() < 0.4) {
      const coin = this.physics.add.sprite(x, y, "coin_tex");
      coin.lootType = "coin";
      coin.value = cfg.coins;
      this.loot.add(coin);
    }
    if (cfg.gems && Math.random() < 0.5 || Math.random() < 0.06) {
      const gem = this.physics.add.sprite(x + 10, y, "gem_tex");
      gem.lootType = "gem";
      gem.value = cfg.gems || 1;
      this.loot.add(gem);
    }
  }

  onCollectLoot(player, item) {
    if (!item.active) return;
    if (item.lootType === "coin") {
      this.sessionCoins += item.value;
    } else {
      this.sessionGems += item.value;
    }
    item.destroy();
    this.updateHUD();
  }

  // ---------------- LEVEL UP ----------------
  checkLevelUp() {
    const needed = 20 + this.sessionLevel * 15;
    if (this.sessionXP >= needed) {
      this.sessionXP -= needed;
      this.sessionLevel += 1;
      this.showUpgradeChoices();
    }
  }

  showUpgradeChoices() {
    this.physics.pause();
    this.spawnEvent.paused = true;
    this.attackEvent.paused = true;

    const choices = pickRandomUpgrades(3);
    const modal = document.getElementById("levelup-modal");
    const optionsEl = document.getElementById("levelup-options");
    optionsEl.innerHTML = "";

    choices.forEach((upg) => {
      const btn = document.createElement("button");
      btn.className = "upgrade-card";
      btn.innerHTML = `<span class="upgrade-icon">${upg.icon}</span><span>${upg.label}</span>`;
      btn.onclick = () => {
        upg.apply(this.stats);
        modal.classList.add("hidden");
        this.physics.resume();
        this.spawnEvent.paused = false;
        this.attackEvent.paused = false;
      };
      optionsEl.appendChild(btn);
    });

    modal.classList.remove("hidden");
  }

  // ---------------- PLAYER DAMAGE ----------------
  onEnemyHitPlayer(player, enemy) {
    const now = this.time.now;
    if (now - enemy.lastHitPlayerAt < 700) return;
    enemy.lastHitPlayerAt = now;

    this.stats.hp -= enemy.damage;
    this.cameras.main.shake(120, 0.004);
    this.updateHUD();

    if (this.stats.hp <= 0 && !this.gameOver) {
      this.endRun(false);
    }
  }

  // ---------------- UPDATE LOOP ----------------
  update() {
    if (this.gameOver) return;

    const vec = Joystick.getVector();
    const speed = this.stats.baseMoveSpeed * this.stats.moveSpeedMult;
    this.player.setVelocity(vec.x * speed, vec.y * speed);

    this.enemies.children.iterate((enemy) => {
      if (!enemy || !enemy.active) return;
      const angle = Phaser.Math.Angle.Between(enemy.x, enemy.y, this.player.x, this.player.y);
      this.physics.velocityFromRotation(angle, enemy.speed, enemy.body.velocity);
    });

    // پاک‌سازی گلوله‌های خارج از دنیا
    this.bullets.children.iterate((b) => {
      if (b && (b.x < 0 || b.x > WORLD_SIZE || b.y < 0 || b.y > WORLD_SIZE)) b.destroy();
    });

    this.updateHUD();
  }

  // ---------------- HUD ----------------
  updateHUD() {
    const hpPct = Math.max(0, this.stats.hp / this.stats.hpMax) * 100;
    HUD.hpFill.style.width = `${hpPct}%`;

    const needed = 20 + this.sessionLevel * 15;
    const xpPct = Math.min(100, (this.sessionXP / needed) * 100);
    HUD.xpFill.style.width = `${xpPct}%`;

    HUD.waveText.textContent = `Wave ${this.currentWave}`;
    HUD.levelText.textContent = `Lv ${this.sessionLevel}`;
    HUD.coinText.textContent = this.sessionCoins;
    HUD.gemText.textContent = this.sessionGems;
  }

  // ---------------- END RUN ----------------
  async endRun(manual) {
    this.gameOver = true;
    this.physics.pause();
    this.spawnEvent.remove();
    this.attackEvent.remove();

    const durationSeconds = Math.round((this.time.now - this.startTime) / 1000);

    const overlay = document.getElementById("gameover-modal");
    document.getElementById("gameover-title").textContent = manual ? "🏳️ بازی تمام شد" : "💀 مرگ";
    document.getElementById("gameover-stats").textContent = "در حال ثبت نتیجه...";
    overlay.classList.remove("hidden");

    try {
      const result = await Network.finishRun({
        waveReached: this.currentWave,
        durationSeconds,
        killsByType: this.killsByType,
      });

      const r = result.rewards;
      document.getElementById("gameover-stats").innerHTML = `
        🌊 Wave رسیده: ${this.currentWave}<br/>
        💰 سکه واقعی گرفته‌شده: ${r.coins_earned}<br/>
        ⭐ XP واقعی گرفته‌شده: ${r.xp_earned}<br/>
        💎 جم گرفته‌شده: ${r.gems_earned}<br/>
        ${r.leveled_up ? "🎉 لول‌آپ حساب!" : ""}
      `;
      playerProfile = result.profile;
    } catch (e) {
      document.getElementById("gameover-stats").textContent = "❌ خطا در ثبت نتیجه. دوباره تلاش کن.";
      console.error(e);
    }
  }
}

// ==================== BOOTSTRAP ====================
async function bootstrap() {
  const tg = window.Telegram && window.Telegram.WebApp;
  if (tg) {
    tg.ready();
    tg.expand();
  }

  HUD.hpFill = document.getElementById("hp-fill");
  HUD.xpFill = document.getElementById("xp-fill");
  HUD.waveText = document.getElementById("wave-text");
  HUD.levelText = document.getElementById("level-text");
  HUD.coinText = document.getElementById("coin-text");
  HUD.gemText = document.getElementById("gem-text");

  Joystick.init(document.getElementById("joystick-zone"), document.getElementById("joystick-knob"));

  const loadingEl = document.getElementById("loading-screen");

  try {
    const authResult = await Network.auth();
    playerProfile = authResult.profile;
  } catch (e) {
    loadingEl.querySelector(".loading-text").textContent = "❌ خطا در اتصال به تلگرام. برنامه را از داخل ربات باز کن.";
    console.error(e);
    return;
  }

  const config = {
    type: Phaser.AUTO,
    parent: "game-container",
    backgroundColor: "#0b0c12",
    scale: {
      mode: Phaser.Scale.RESIZE,
      width: window.innerWidth,
      height: window.innerHeight,
    },
    physics: {
      default: "arcade",
      arcade: { gravity: { x: 0, y: 0 }, debug: false },
    },
    scene: [GameScene],
  };

  new Phaser.Game(config);
  loadingEl.classList.add("hidden");
}

document.getElementById("retry-btn").addEventListener("click", () => window.location.reload());
document.addEventListener("DOMContentLoaded", bootstrap);