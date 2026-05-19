-- ============================================================
-- Migration: Add reminder_times to user_settings + allow user_id=0
-- Run this if you get 500 errors on /api/push/reminder-times
-- or /api/push/admin-defaults
--
-- Safe to run multiple times.
-- Usage:
--   mysql -u root -p cal_ai < migrate_add_reminder_times.sql
-- ============================================================

USE `cal_ai`;

-- 1. Create user_settings if it doesn't exist yet (no-op if it does)
CREATE TABLE IF NOT EXISTS `user_settings` (
  `user_id`        INT PRIMARY KEY,
  `reminder_times` TEXT DEFAULT NULL,
  `updated_at`     DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. Add reminder_times column if missing (existing installs)
ALTER TABLE `user_settings`
  ADD COLUMN IF NOT EXISTS `reminder_times` TEXT DEFAULT NULL;

-- 3. Drop the FK constraint on user_id so user_id=0 sentinel is allowed.
--    We do this dynamically because the constraint name varies.
SET @fk := (
    SELECT CONSTRAINT_NAME
    FROM information_schema.KEY_COLUMN_USAGE
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME   = 'user_settings'
      AND COLUMN_NAME  = 'user_id'
      AND REFERENCED_TABLE_NAME = 'users'
    LIMIT 1
);
SET @drop_fk = IF(
    @fk IS NOT NULL,
    CONCAT('ALTER TABLE `user_settings` DROP FOREIGN KEY `', @fk, '`'),
    'SELECT 1 -- no FK to drop'
);
PREPARE stmt FROM @drop_fk;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 4. Ensure column type is plain INT NOT NULL (no FK definition left)
ALTER TABLE `user_settings` MODIFY `user_id` INT NOT NULL;

SELECT 'Migration complete. user_id=0 sentinel is now allowed.' AS result;
