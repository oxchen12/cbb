# Scratch Space

## Plays

### Types

* Shot
  * Types
    * 2fg
      * layup
      * dunk
      * hook shot
      * jump shot
    * 3fg
    * ft
  * Parameters
    * Shooter
    * Assister?
    * Made/missed
* Rebound
  * Types
    * oreb
    * dreb
  * Parameters
    * Committer
* Turnover
  * Types
    * bad pass
    * lost ball
    * traveling
    * offensive foul
  * Parameters
    * Committer
    * Stealer?
* Foul
  * Types
    * Personal
    * Shooting
    * Offensive
    * Technical?
    * Flagrant?
  * Parameters
    * Committer
    * Drawer
* Timeout
  * Type
  * Parameters
    * Team/TV
* Jump ball/tipoff
* End of period

### Regexes

* Name: ((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+)
* Shot: r"((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+) (makes|misses) (two point|three point|regular free throw) ([A-Za-z0-9 ]+[A-Za-z0-9])(?: \(((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+) assists\))?"