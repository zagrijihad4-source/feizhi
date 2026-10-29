#include <windows.h>
int test(void){
    __try { int *p = 0; *p = 1; }
    __except (EXCEPTION_EXECUTE_HANDLER) { return 0; }
    return 1;
}
