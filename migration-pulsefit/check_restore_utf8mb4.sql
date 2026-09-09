SET NAMES utf8mb4;
SELECT COUNT(1) AS people_count FROM pulsefit_gym.people;
SELECT COUNT(1) AS customer_count FROM pulsefit_gym.customers;
SELECT COUNT(1) AS membership_count FROM pulsefit_gym.memberships;
SHOW VARIABLES LIKE 'character_set_database';
SHOW VARIABLES LIKE 'collation_database';
SELECT display_name FROM pulsefit_gym.people WHERE display_name REGEXP '[^ -~]' LIMIT 5;
