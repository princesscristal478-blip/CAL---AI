-- ============================================================
-- Migration: Add goal_weight and start_weight to users table
-- Run this if you get: "Unknown column 'goal_weight' in 'field list'"
--
-- Safe to run multiple times (uses ADD COLUMN IF NOT EXISTS)
-- Usage:
--   mysql -u root -p cal_ai < migrate_add_goal_weight.sql
-- ============================================================

USE `cal_ai`;

ALTER TABLE `users`
  ADD COLUMN IF NOT EXISTS `goal_weight`  FLOAT DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS `start_weight` FLOAT DEFAULT NULL;
