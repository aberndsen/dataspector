      ******************************************************************
      * SAMPLE MAINFRAME ACCOUNT VECTOR COPYBOOK                       *
      ******************************************************************
       01  ACCOUNT-RECORD.
           05  ACCT-KEY.
               10  ACCT-REGION            PIC XX.
               10  ACCT-NUMBER            PIC X(7).
               10  ACCT-CHECK-DIGIT       PIC X.
               10  FILLER                 PIC XX.
           05  ACCT-STATUS                PIC X.
               88  ACCT-ACTIVE            VALUE 'A'.
               88  ACCT-CLOSED            VALUE 'C'.
           05  ACCT-EFF-DATE              PIC 9(8).
           05  ACCT-EFF-DATE-PARTS REDEFINES ACCT-EFF-DATE.
               10  ACCT-EFF-YEAR          PIC 9(4).
               10  ACCT-EFF-MONTH         PIC 9(2).
               10  ACCT-EFF-DAY           PIC 9(2).
           05  ACCT-ADJUSTMENT            PIC S9(5)V99.
           05  ACCT-TERM-MONTHS           PIC S9(4)    COMP.
           05  ACCT-SCORE                 PIC S9(9)    COMP.
           05  ACCT-RATE                  USAGE COMP-1.
           05  ACCT-FACTOR                USAGE COMP-2.
           05  ACCT-BALANCE               PIC S9(9)V99 COMP-3.
           05  ACCT-PERIODS OCCURS 3 TIMES.
               10  PERIOD-AMT             PIC S9(7)V99 COMP-3.
