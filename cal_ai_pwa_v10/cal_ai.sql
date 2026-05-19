-- ============================================================
-- Cal AI PWA — MySQL Database Schema + Seed Data
-- Import this via phpMyAdmin or MySQL CLI:
--   mysql -u root -p < cal_ai.sql
-- ============================================================

CREATE DATABASE IF NOT EXISTS `cal_ai`
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE `cal_ai`;

-- ─── Tables ──────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS `users` (
  `id`            INT AUTO_INCREMENT PRIMARY KEY,
  `username`      VARCHAR(80)  NOT NULL UNIQUE,
  `email`         VARCHAR(120) NOT NULL UNIQUE,
  `password_hash` VARCHAR(256) NOT NULL,
  `age`           FLOAT DEFAULT 25,
  `weight`        FLOAT DEFAULT 70,
  `height`        FLOAT DEFAULT 170,
  `gender`        VARCHAR(10)  DEFAULT 'male',
  `goal`          VARCHAR(20)  DEFAULT 'maintain',
  `activity`      VARCHAR(20)  DEFAULT 'moderate',
  `goal_weight`   FLOAT DEFAULT NULL,
  `start_weight`  FLOAT DEFAULT NULL,
  `created_at`    DATETIME     DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `foods` (
  `id`       INT AUTO_INCREMENT PRIMARY KEY,
  `name`     VARCHAR(150) NOT NULL,
  `calories` FLOAT NOT NULL,
  `protein`  FLOAT DEFAULT 0,
  `carbs`    FLOAT DEFAULT 0,
  `fat`      FLOAT DEFAULT 0,
  `fiber`    FLOAT DEFAULT 0,
  `category` VARCHAR(60)  DEFAULT 'General',
  `source`   VARCHAR(60)  DEFAULT 'Manual',
  INDEX `idx_name`     (`name`),
  INDEX `idx_category` (`category`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `food_logs` (
  `id`        INT AUTO_INCREMENT PRIMARY KEY,
  `user_id`   INT NOT NULL,
  `food_id`   INT NOT NULL,
  `quantity`  FLOAT    DEFAULT 100,
  `meal_type` VARCHAR(20) DEFAULT 'Snack',
  `logged_at` DATETIME    DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`food_id`) REFERENCES `foods`(`id`),
  INDEX `idx_user_date` (`user_id`, `logged_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `push_subscriptions` (
  `id`                INT AUTO_INCREMENT PRIMARY KEY,
  `user_id`           INT NOT NULL UNIQUE,
  `subscription_json` TEXT NOT NULL,
  `created_at`        DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `meal_plans` (
  `id`         INT AUTO_INCREMENT PRIMARY KEY,
  `user_id`    INT NOT NULL,
  `plan_json`  MEDIUMTEXT NOT NULL,
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ─── Weight Logs ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `weight_logs` (
  `id`        INT AUTO_INCREMENT PRIMARY KEY,
  `user_id`   INT NOT NULL,
  `weight`    FLOAT NOT NULL,
  `logged_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY `uq_user_day` (`user_id`, DATE(`logged_at`)),
  FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
  INDEX `idx_user_date` (`user_id`, `logged_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ─── User Settings (custom reminder times) ────────────────────────────────────
CREATE TABLE IF NOT EXISTS `user_settings` (
  `user_id`        INT PRIMARY KEY,
  `reminder_times` TEXT DEFAULT NULL,
  `updated_at`     DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ─── Seed Data: Foods ─────────────────────────────────────────────────────────

INSERT INTO `foods` (`name`, `calories`, `protein`, `carbs`, `fat`, `fiber`, `category`, `source`) VALUES

-- Fruits
('Apple',          52,  0.3, 14.0,  0.2, 2.4, 'Fruits', 'Seed'),
('Banana',         89,  1.1, 23.0,  0.3, 2.6, 'Fruits', 'Seed'),
('Orange',         47,  0.9, 12.0,  0.1, 2.4, 'Fruits', 'Seed'),
('Mango',          60,  0.8, 15.0,  0.4, 1.6, 'Fruits', 'Seed'),
('Watermelon',     30,  0.6,  7.6,  0.2, 0.4, 'Fruits', 'Seed'),
('Avocado',       160,  2.0,  9.0, 15.0, 6.7, 'Fruits', 'Seed'),
('Papaya',         43,  0.5, 11.0,  0.3, 1.7, 'Fruits', 'Seed'),
('Strawberry',     32,  0.7,  7.7,  0.3, 2.0, 'Fruits', 'Seed'),
('Pineapple',      50,  0.5, 13.0,  0.1, 1.4, 'Fruits', 'Seed'),
('Grapes',         69,  0.7, 18.0,  0.2, 0.9, 'Fruits', 'Seed'),

-- Vegetables
('Broccoli',       34,  2.8,  6.6,  0.4, 2.6, 'Vegetables', 'Seed'),
('Carrot',         41,  0.9,  9.6,  0.2, 2.8, 'Vegetables', 'Seed'),
('Spinach',        23,  2.9,  3.6,  0.4, 2.2, 'Vegetables', 'Seed'),
('Tomato',         18,  0.9,  3.9,  0.2, 1.2, 'Vegetables', 'Seed'),
('Potato',         77,  2.0, 17.0,  0.1, 2.2, 'Vegetables', 'Seed'),
('Sweet Potato',   86,  1.6, 20.0,  0.1, 3.0, 'Vegetables', 'Seed'),
('Onion',          40,  1.1,  9.3,  0.1, 1.7, 'Vegetables', 'Seed'),
('Cucumber',       15,  0.7,  3.6,  0.1, 0.5, 'Vegetables', 'Seed'),
('Bell Pepper',    31,  1.0,  6.0,  0.3, 2.1, 'Vegetables', 'Seed'),
('Corn',           86,  3.2, 19.0,  1.2, 2.7, 'Vegetables', 'Seed'),
('Kangkong',       19,  2.6,  3.1,  0.2, 1.8, 'Vegetables', 'Seed'),
('Ampalaya',       17,  1.0,  3.7,  0.2, 2.8, 'Vegetables', 'Seed'),
('Pechay',         13,  1.5,  2.2,  0.2, 1.0, 'Vegetables', 'Seed'),
('Sitaw',          47,  2.7,  8.4,  0.4, 3.4, 'Vegetables', 'Seed'),
('Talong',         25,  1.0,  6.0,  0.2, 3.0, 'Vegetables', 'Seed'),

-- Grains
('White Rice (cooked)',     130, 2.7, 28.0, 0.3, 0.4, 'Grains', 'Seed'),
('Brown Rice (cooked)',     123, 2.7, 26.0, 1.0, 1.8, 'Grains', 'Seed'),
('Oatmeal (cooked)',         71, 2.5, 12.0, 1.5, 1.7, 'Grains', 'Seed'),
('Pandesal',                300, 9.0, 55.0, 5.0, 2.0, 'Grains', 'Seed'),
('Tasty Bread',             265, 9.0, 49.0, 3.2, 2.7, 'Grains', 'Seed'),
('Whole Wheat Bread',       247,13.0, 41.0, 4.2, 7.0, 'Grains', 'Seed'),
('Pancit Canton (cooked)',  175, 8.0, 28.0, 4.0, 1.5, 'Grains', 'Seed'),
('Pasta (cooked)',          158, 5.8, 31.0, 0.9, 1.8, 'Grains', 'Seed'),
('Corn Tortilla',           218, 5.7, 45.0, 2.9, 6.3, 'Grains', 'Seed'),

-- Protein
('Chicken Breast (cooked)', 165,31.0,  0.0,  3.6, 0.0, 'Protein', 'Seed'),
('Egg (boiled)',            155,13.0,  1.1, 11.0, 0.0, 'Protein', 'Seed'),
('Beef (ground, cooked)',   254,26.0,  0.0, 17.0, 0.0, 'Protein', 'Seed'),
('Tuna (canned)',           132,29.0,  0.0,  1.0, 0.0, 'Protein', 'Seed'),
('Salmon (cooked)',         208,20.0,  0.0, 13.0, 0.0, 'Protein', 'Seed'),
('Pork (cooked)',           242,27.0,  0.0, 14.0, 0.0, 'Protein', 'Seed'),
('Tofu',                    76, 8.1,  1.9,  4.8, 0.3, 'Protein', 'Seed'),
('Shrimp (cooked)',          99,24.0,  0.0,  0.3, 0.0, 'Protein', 'Seed'),
('Lentils (cooked)',        116, 9.0, 20.0,  0.4, 7.9, 'Protein', 'Seed'),
('Black Beans (cooked)',    132, 8.9, 24.0,  0.5, 8.7, 'Protein', 'Seed'),
('Chickpeas (cooked)',      164, 8.9, 27.0,  2.6, 7.6, 'Protein', 'Seed'),

-- Dairy
('Whole Milk',              61,  3.2,  4.8,  3.3, 0.0, 'Dairy', 'Seed'),
('Skim Milk',               35,  3.4,  5.0,  0.1, 0.0, 'Dairy', 'Seed'),
('Cheddar Cheese',         403, 25.0,  1.3, 33.0, 0.0, 'Dairy', 'Seed'),
('Eden Cheese',            350, 22.0,  2.0, 28.0, 0.0, 'Dairy', 'Seed'),
('Greek Yogurt (plain)',    97,  9.0,  6.0,  5.0, 0.0, 'Dairy', 'Seed'),
('Butter',                 717,  0.9,  0.1, 81.0, 0.0, 'Dairy', 'Seed'),
('Mozzarella',             280, 18.0,  3.1, 22.0, 0.0, 'Dairy', 'Seed'),
('Ice Cream (vanilla)',    207,  3.5, 24.0, 11.0, 0.7, 'Dairy', 'Seed'),

-- Beverages
('Milo (per serving)',     180,  4.0, 30.0,  4.5, 2.0, 'Beverages', 'Seed'),
('Buko Juice',              19,  0.7,  3.7,  0.2, 1.1, 'Beverages', 'Seed'),
('Orange Juice',            45,  0.7, 10.0,  0.2, 0.2, 'Beverages', 'Seed'),
('Softdrink (regular)',     37,  0.0,  9.6,  0.0, 0.0, 'Beverages', 'Seed'),
('Coffee (black)',           2,  0.3,  0.0,  0.0, 0.0, 'Beverages', 'Seed'),
('Green Tea',                1,  0.2,  0.2,  0.0, 0.0, 'Beverages', 'Seed'),
('Beer (regular)',           43, 0.5,  3.6,  0.0, 0.0, 'Beverages', 'Seed'),

-- Snacks
('Potato Chips',           536,  7.0, 53.0, 35.0, 4.8, 'Snacks', 'Seed'),
('Chicharon',              544, 32.0,  0.0, 46.0, 0.0, 'Snacks', 'Seed'),
('Polvoron',               490,  6.0, 62.0, 24.0, 1.0, 'Snacks', 'Seed'),
('Chocolate (dark)',       546,  5.0, 60.0, 31.0, 7.0, 'Snacks', 'Seed'),
('Peanuts (roasted)',      567, 26.0, 16.0, 49.0, 8.5, 'Snacks', 'Seed'),
('Almonds',                579, 21.0, 22.0, 50.0,12.0, 'Snacks', 'Seed'),
('Granola Bar',            393,  8.3, 64.0, 14.0, 4.4, 'Snacks', 'Seed'),
('Donut (glazed)',         452,  5.0, 51.0, 25.0, 1.3, 'Snacks', 'Seed'),

-- Filipino Foods
('Adobo (Chicken)',        190, 18.0,  5.0, 11.0, 0.5, 'Filipino', 'Seed'),
('Sinangag (Garlic Rice)', 180,  3.5, 38.0,  2.5, 0.5, 'Filipino', 'Seed'),
('Sinigang (Pork)',        145, 14.0,  8.0,  7.0, 1.5, 'Filipino', 'Seed'),
('Kare-Kare',              220, 20.0, 10.0, 12.0, 2.0, 'Filipino', 'Seed'),
('Lumpia Shanghai',        195,  9.0, 18.0, 10.0, 1.0, 'Filipino', 'Seed'),
('Lechon (Pork)',          310, 22.0,  0.0, 24.0, 0.0, 'Filipino', 'Seed'),
('Tinola (Chicken)',       120, 16.0,  5.0,  4.0, 1.0, 'Filipino', 'Seed'),
('Bangus (Milkfish, grilled)', 148, 21.0, 0.0, 7.0, 0.0, 'Filipino', 'Seed'),
('Tinapa (Smoked Fish)',   180, 24.0,  0.0,  9.0, 0.0, 'Filipino', 'Seed'),
('Daing na Bangus',        220, 28.0,  0.0, 12.0, 0.0, 'Filipino', 'Seed'),
('Pinakbet',                85,  4.0, 10.0,  3.5, 3.0, 'Filipino', 'Seed'),
('Bistek Tagalog',         210, 22.0,  6.0, 11.0, 0.5, 'Filipino', 'Seed'),
('Caldereta (Beef)',       280, 24.0, 12.0, 15.0, 2.0, 'Filipino', 'Seed'),
('Mechado',                250, 22.0, 10.0, 14.0, 1.5, 'Filipino', 'Seed'),
('Menudo',                 200, 18.0, 15.0,  8.0, 2.0, 'Filipino', 'Seed'),
('Champorado',             220,  4.0, 44.0,  4.0, 2.5, 'Filipino', 'Seed'),
('Halo-Halo',              250,  3.5, 48.0,  6.0, 1.5, 'Filipino', 'Seed'),
('Bibingka',               215,  4.5, 38.0,  5.5, 1.0, 'Filipino', 'Seed'),
('Puto',                   180,  4.0, 34.0,  3.0, 0.5, 'Filipino', 'Seed'),
('Mango Float',            280,  3.0, 40.0, 13.0, 0.8, 'Filipino', 'Seed'),
('Leche Flan',             310,  7.0, 42.0, 13.0, 0.0, 'Filipino', 'Seed'),
('Biko',                   295,  3.5, 58.0,  6.0, 1.0, 'Filipino', 'Seed'),
('Arroz Caldo',            160, 12.0, 22.0,  3.0, 1.0, 'Filipino', 'Seed'),
('Lugaw',                  120,  5.0, 22.0,  1.5, 0.5, 'Filipino', 'Seed'),
('Bulalo',                 185, 20.0,  3.0, 10.0, 0.5, 'Filipino', 'Seed'),
('Nilaga (Beef)',           165, 18.0,  8.0,  7.0, 2.0, 'Filipino', 'Seed'),
('Tokwa at Baboy',         220, 16.0,  5.0, 15.0, 1.0, 'Filipino', 'Seed'),
('Pancit Bihon',           170,  7.0, 28.0,  3.5, 1.5, 'Filipino', 'Seed'),
('Pancit Palabok',         210,  9.0, 32.0,  5.5, 1.0, 'Filipino', 'Seed'),
('Dinuguan',               230, 18.0,  5.0, 16.0, 0.5, 'Filipino', 'Seed'),
('Crispy Pata',            420, 30.0,  3.0, 32.0, 0.0, 'Filipino', 'Seed'),
('Sisig',                  310, 24.0,  4.0, 22.0, 0.5, 'Filipino', 'Seed'),
('Laing',                  260, 10.0,  8.0, 22.0, 3.5, 'Filipino', 'Seed'),
('Paksiw na Isda',         130, 18.0,  4.0,  5.0, 0.5, 'Filipino', 'Seed'),
('Inihaw na Liempo',       380, 22.0,  0.0, 32.0, 0.0, 'Filipino', 'Seed'),
('Tortang Talong',         155, 10.0,  6.0, 10.0, 2.0, 'Filipino', 'Seed'),
('Ginisang Munggo',        130,  8.5, 18.0,  3.0, 5.0, 'Filipino', 'Seed'),
('Goto',                   155, 12.0, 18.0,  4.0, 0.5, 'Filipino', 'Seed');

-- ── Upgrade additions (run these if upgrading from an older schema) ──────────

ALTER TABLE `users`
  ADD COLUMN IF NOT EXISTS `goal_weight`      FLOAT        DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS `start_weight`     FLOAT        DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS `totp_secret`      VARCHAR(64)  DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS `totp_enabled`     TINYINT(1)   DEFAULT 0,
  ADD COLUMN IF NOT EXISTS `is_locked`        TINYINT(1)   DEFAULT 0,
  ADD COLUMN IF NOT EXISTS `failed_attempts`  INT          DEFAULT 0,
  ADD COLUMN IF NOT EXISTS `locked_until`     DATETIME     DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS `last_login`       DATETIME     DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS `last_login_ip`    VARCHAR(45)  DEFAULT NULL;

CREATE TABLE IF NOT EXISTS `password_reset_tokens` (
  `id`         INT AUTO_INCREMENT PRIMARY KEY,
  `user_id`    INT          NOT NULL,
  `token_hash` VARCHAR(128) NOT NULL UNIQUE,
  `expires_at` DATETIME     NOT NULL,
  `used`       TINYINT(1)   DEFAULT 0,
  `created_at` DATETIME     DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `login_attempts` (
  `id`         INT AUTO_INCREMENT PRIMARY KEY,
  `ip_address` VARCHAR(45)  NOT NULL,
  `email`      VARCHAR(120) DEFAULT NULL,
  `attempted_at` DATETIME   DEFAULT CURRENT_TIMESTAMP,
  `success`    TINYINT(1)   DEFAULT 0,
  INDEX idx_ip (ip_address),
  INDEX idx_email (email),
  INDEX idx_time (attempted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `two_factor_pending` (
  `id`         INT AUTO_INCREMENT PRIMARY KEY,
  `user_id`    INT          NOT NULL,
  `token`      VARCHAR(64)  NOT NULL UNIQUE,
  `expires_at` DATETIME     NOT NULL,
  `created_at` DATETIME     DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ─── Allow user_id = 0 for admin default reminder times ──────────────────────
-- (user_id=0 is the sentinel for global admin defaults)
-- Step 1: Remove the FK by name (default InnoDB auto-name)
ALTER TABLE `user_settings` DROP FOREIGN KEY IF EXISTS `user_settings_ibfk_1`;
-- Step 2: Also drop any FK constraint whose name matches the column pattern
-- (covers cases where the constraint was auto-named differently)
SET @fk := (
    SELECT CONSTRAINT_NAME
    FROM information_schema.KEY_COLUMN_USAGE
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'user_settings'
      AND COLUMN_NAME = 'user_id'
      AND REFERENCED_TABLE_NAME = 'users'
    LIMIT 1
);
SET @drop_fk = IF(
    @fk IS NOT NULL,
    CONCAT('ALTER TABLE `user_settings` DROP FOREIGN KEY `', @fk, '`'),
    'SELECT 1'  -- no-op
);
PREPARE stmt FROM @drop_fk;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
-- Step 3: Ensure user_id column is plain INT NOT NULL (no FK)
ALTER TABLE `user_settings` MODIFY `user_id` INT NOT NULL;
