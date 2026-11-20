      ******************************************************************
      * SAMPLE EXOTIC COBOL DATA TYPES COPYBOOK                        *
      * Covers COMP-6, COMP-X, external float, BINARY-CHAR/SHORT/LONG/ *
      * DOUBLE, FLOAT-SHORT/LONG, PIC U (UTF-8), PIC G (DBCS),         *
      * PIC 1 (BIT), and FUNCTION-POINTER.                             *
      ******************************************************************
       01  EXOTIC-RECORD.
           05  REC-TAG                PIC X(4).
           05  PACKED-UNSIGNED-CNT    PIC 9(7)        USAGE COMP-6.
           05  PACKED-UNSIGNED-AMT    PIC 9(4)V99     USAGE COMP-6.
           05  VAR-BIN-24BIT          PIC X(3)        USAGE COMP-X.
           05  VAR-BIN-DIGITS         PIC 9(5)        USAGE COMP-X.
           05  EXT-FLOAT-SCI          PIC +9.9(5)E+99 USAGE DISPLAY.
           05  EXT-FLOAT-IMPLIED      PIC +9(2)V99E+99 USAGE DISPLAY.
           05  C-INT8                 USAGE BINARY-CHAR.
           05  C-UINT8                USAGE BINARY-CHAR UNSIGNED.
           05  C-INT16                USAGE BINARY-SHORT SIGNED.
           05  C-UINT32               USAGE BINARY-LONG UNSIGNED.
           05  C-INT64                USAGE BINARY-DOUBLE.
           05  IEEE-SINGLE            USAGE FLOAT-SHORT.
           05  IEEE-DOUBLE            USAGE FLOAT-LONG.
           05  UTF8-FIXED-CHARS       PIC U(4).
           05  UTF8-FIXED-BYTES       PIC U BYTE-LENGTH 12 USAGE UTF-8.
           05  DBCS-KANJI             PIC G(3)        USAGE DISPLAY-1.
           05  FLAG-BYTE              PIC 1(8)        USAGE BIT.
           05  FLAG-12BIT             PIC 1(12)       USAGE BIT.
           05  CALLBACK-PTR           USAGE FUNCTION-POINTER.
