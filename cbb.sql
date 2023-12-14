CREATE TABLE Teams (
	tid text,
	name text,
	mascot text
);

CREATE TABLE Games (
	gid integer PRIMARY KEY AUTOINCREMENT,
	cbs_id text,
	neutral boolean,
	home text,
	away text
);

CREATE TABLE Players (
	pid integer PRIMARY KEY AUTOINCREMENT,
	fname text,
	lname text,
	num integer,
	pos varchar,
	htfeet integer,
	htin integer,
	wt integer,
	class varchar,
	hometown text,
	tid text
);
