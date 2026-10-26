// Host mocks for testing homekey_bridge.h
#pragma once
#include <string>
#include <cstring>
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <chrono>
#include <thread>
#include <sys/socket.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <fcntl.h>
#include <poll.h>
inline unsigned long millis(){ using namespace std::chrono; static auto t0=steady_clock::now(); return duration_cast<milliseconds>(steady_clock::now()-t0).count(); }
inline void delay(unsigned long ms){ std::this_thread::sleep_for(std::chrono::milliseconds(ms)); }
class String : public std::string { public:
  String(){} String(const char*s):std::string(s){} String(const std::string&s):std::string(s){} String(int v):std::string(std::to_string(v)){}
  String substring(size_t a,size_t b) const { return String(std::string::substr(a,b-a)); }
  String toString() const { return *this; }
};
inline String operator+(const String&a,const char*b){return String(std::string(a)+b);}
inline String operator+(const char*a,const String&b){return String(std::string(a)+std::string(b));}
inline String operator+(const String&a,const String&b){return String(std::string(a)+std::string(b));}
struct { void println(const String&s){ printf("[lock] %s\n", s.c_str()); fflush(stdout);} } Serial;
struct { void addService(const char*,const char*,int){} } MDNS;
class WiFiClient { public: int fd=-1;
  bool connected(){ if(fd<0) return false; char c; int r=recv(fd,&c,1,MSG_PEEK|MSG_DONTWAIT); if(r==0){close(fd);fd=-1;return false;} return true; }
  int available(){ if(fd<0) return 0; char b[4096]; int r=recv(fd,b,sizeof b,MSG_PEEK|MSG_DONTWAIT); return r>0?r:0; }
  int read(){ unsigned char c; return recv(fd,&c,1,0)==1?c:-1; }
  size_t write(const void*d,size_t n){ return fd<0?0:send(fd,d,n,0); }
  void stop(){ if(fd>=0) close(fd); fd=-1; }
  void setNoDelay(bool){}
  String remoteIP(){ return "127.0.0.1"; }
};
class WiFiServer { int fd=-1; uint16_t port; public: WiFiServer(uint16_t p):port(p){}
  void begin(){ fd=socket(AF_INET,SOCK_STREAM,0); int o=1; setsockopt(fd,SOL_SOCKET,SO_REUSEADDR,&o,4); sockaddr_in a{}; a.sin_family=AF_INET; a.sin_port=htons(port); a.sin_addr.s_addr=htonl(INADDR_LOOPBACK); bind(fd,(sockaddr*)&a,sizeof a); listen(fd,4); fcntl(fd,F_SETFL,O_NONBLOCK); }
  bool hasClient(){ pollfd p{fd,POLLIN,0}; return poll(&p,1,0)>0; }
  WiFiClient accept(){ WiFiClient c; c.fd=::accept(fd,nullptr,nullptr); return c; }
};
