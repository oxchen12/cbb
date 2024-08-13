CREATE TABLE IF NOT EXISTS Teams (
	tid integer primary key NOT NULL UNIQUE,
	cid INTEGER NOT NULL,
	name TEXT NOT NULL,
	mascot TEXT NOT NULL,
	FOREIGN KEY (cid) REFERENCES Conferences(cid)
);
CREATE TABLE IF NOT EXISTS Games (
	gid integer primary key NOT NULL UNIQUE,
	neutral REAL NOT NULL DEFAULT false,
	home INTEGER NOT NULL,
	away INTEGER NOT NULL,
	date TEXT NOT NULL,
	year INTEGER NOT NULL,
	FOREIGN KEY (home) REFERENCES Teams(tid),
	FOREIGN KEY (away) REFERENCES Teams(tid)
);
CREATE TABLE IF NOT EXISTS Players (
	pid integer primary key NOT NULL UNIQUE,
	fname TEXT NOT NULL,
	lname TEXT NOT NULL,
	pos TEXT NOT NULL,
	htfeet INTEGER NOT NULL,
	htin INTEGER NOT NULL,
	wt INTEGER NOT NULL,
	fresh_year INTEGER,
	hometown TEXT
);
CREATE TABLE IF NOT EXISTS Plays (
	plid integer primary key NOT NULL UNIQUE,
	gid INTEGER NOT NULL,
	tid INTEGER,
	period INTEGER NOT NULL,
	time_min INTEGER NOT NULL,
	time_sec INTEGER NOT NULL,
	type TEXT NOT NULL,
	subtype TEXT NOT NULL,
	away_score INTEGER NOT NULL,
	home_score INTEGER NOT NULL,
	pts_scored INTEGER NOT NULL,
	desc TEXT NOT NULL,
	plyr INTEGER,
	plyr_ast INTEGER,
	FOREIGN KEY (gid) REFERENCES Games(gid),
	FOREIGN KEY (tid) REFERENCES Teams(tid),
	FOREIGN KEY (plyr) REFERENCES Players(pid),
	FOREIGN KEY (plyr_ast) REFERENCES Players(pid)
);
CREATE TABLE IF NOT EXISTS Conferences (
	cid integer primary key NOT NULL UNIQUE,
	name TEXT NOT NULL UNIQUE,
	abbrev TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS Rosters (
	rid integer NOT NULL UNIQUE,
	tid INTEGER NOT NULL,
	year INTEGER NOT NULL,
	FOREIGN KEY (tid) REFERENCES Teams(tid),
	PRIMARY KEY (rid, tid, year)
);
CREATE TABLE IF NOT EXISTS PlayerSeasons (
	pid INTEGER NOT NULL,
	rid INTEGER NOT NULL,
	num INTEGER NOT NULL,
	FOREIGN KEY (pid) REFERENCES Players(pid),
	FOREIGN KEY (rid) REFERENCES Roster(rid),
	PRIMARY KEY (pid, rid)
);
